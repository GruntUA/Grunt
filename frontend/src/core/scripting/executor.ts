/**
 * Client Script executor — runs user-defined JS in the form context.
 *
 * Client scripts are fetched from the backend per DocType and executed
 * within a controlled scope providing form helpers.
 *
 * Available in scripts:
 * - `cur_frm` / `frm` — current form proxy (get_value, set_value, add_button, etc.)
 * - `grunt` / `frappe` — framework helpers (call, throw, confirm, msgprint, show_alert)
 */

import client from '@/core/api/client'

// ── Types ────────────────────────────────────────────────────────────────

export interface ScriptButton {
  label: string
  action: () => void | Promise<void>
  variant?: string
}

/** Form proxy exposed to client scripts as `cur_frm`. */
export interface FormProxy {
  doctype: string
  doc: Record<string, unknown>
  fields: Record<string, unknown>[]
  is_new: boolean
  get_value: (fieldname: string) => unknown
  set_value: (fieldname: string, value: unknown) => void
  toggle_display: (fieldname: string, show: boolean) => void
  toggle_reqd: (fieldname: string, reqd: boolean) => void
  set_df_property: (fieldname: string, prop: string, value: unknown) => void
  refresh_field: (fieldname: string) => void
  add_button: (label: string, action: () => void | Promise<void>, options?: { variant?: string }) => void
  save: () => Promise<void>
  /** Internal state modified by scripts */
  _display: Record<string, boolean>
  _reqd: Record<string, boolean>
  _df_props: Record<string, Record<string, unknown>>
}

/** Framework helpers exposed as `grunt`. */
export interface GruntProxy {
  call: (opts: { method: string; args?: Record<string, unknown> }) => Promise<unknown>
  throw: (msg: string) => never
  confirm: (msg: string, title?: string) => Promise<boolean>
  msgprint: (msgOrOpts: string | { message: string; title?: string; indicator?: string }) => Promise<void>
  show_alert: (msg: string, type?: 'success' | 'error' | 'info' | 'warning') => void
  prompt: (labelOrOpts: string | { label: string; fieldtype?: string; title?: string }, title?: string) => Promise<string | null>
  warn: (title: string, message: string, primaryLabel?: string) => Promise<boolean>
  form: (opts: { title: string; fields: unknown[]; primaryLabel?: string; size?: string }) => Promise<Record<string, unknown> | null>
  show_progress: (title: string, count: number, total: number, description?: string) => void
}

export type ClientScriptEvent = 'on_load' | 'on_change' | 'validate' | 'before_save' | 'after_save'

interface ClientScriptEntry {
  name: string
  script: string
}

/** Cache: doctype -> scripts */
const scriptCache = new Map<string, ClientScriptEntry[]>()

// ── Script loading ───────────────────────────────────────────────────────

/**
 * Fetch client scripts for a DocType from the backend.
 */
export async function loadClientScripts(doctype: string): Promise<ClientScriptEntry[]> {
  if (scriptCache.has(doctype)) {
    return scriptCache.get(doctype)!
  }

  try {
    const { data } = await client.get<{ data: ClientScriptEntry[] }>(
      `/api/v1/client-script/${encodeURIComponent(doctype)}`
    )
    const scripts = data?.data ?? []
    scriptCache.set(doctype, scripts)
    return scripts
  } catch {
    return []
  }
}

/**
 * Clear cached scripts (e.g. after creating/updating a client script).
 */
export function clearScriptCache(doctype?: string): void {
  if (doctype) {
    scriptCache.delete(doctype)
  } else {
    scriptCache.clear()
  }
}

// ── Proxy factories ──────────────────────────────────────────────────────

/**
 * Create a FormProxy from current form state.
 */
export function createFormProxy(
  doctype: string,
  doc: Record<string, unknown>,
  fields: Record<string, unknown>[],
  callbacks: {
    setValue?: (field: string, value: unknown) => void
    refreshField?: (field: string) => void
    addButton?: (label: string, action: () => void | Promise<void>, options?: { variant?: string }) => void
    save?: () => Promise<void>
  } = {},
  isNew: boolean = false,
): FormProxy {
  const proxy: FormProxy = {
    doctype,
    doc,
    fields,
    is_new: isNew,
    _display: {},
    _reqd: {},
    _df_props: {},

    get_value(fieldname: string) {
      return proxy.doc[fieldname]
    },

    set_value(fieldname: string, value: unknown) {
      proxy.doc[fieldname] = value
      callbacks.setValue?.(fieldname, value)
    },

    toggle_display(fieldname: string, show: boolean) {
      proxy._display[fieldname] = show
    },

    toggle_reqd(fieldname: string, reqd: boolean) {
      proxy._reqd[fieldname] = reqd
    },

    set_df_property(fieldname: string, prop: string, value: unknown) {
      if (!proxy._df_props[fieldname]) {
        proxy._df_props[fieldname] = {}
      }
      proxy._df_props[fieldname][prop] = value
    },

    refresh_field(fieldname: string) {
      callbacks.refreshField?.(fieldname)
    },

    add_button(label: string, action: () => void | Promise<void>, options?: { variant?: string }) {
      callbacks.addButton?.(label, action, options)
    },

    async save() {
      await callbacks.save?.()
    },
  }

  return proxy
}

/**
 * Create the `grunt` helper proxy.
 */
export function createGruntProxy(
  callbacks: {
    msgprint?: (msgOrOpts: string | { message: string; title?: string; indicator?: string }) => Promise<void>
    confirm?: (msg: string, title?: string) => Promise<boolean>
    showAlert?: (msg: string, type?: 'success' | 'error' | 'info' | 'warning') => void
    prompt?: (labelOrOpts: string | { label: string; fieldtype?: string; title?: string }, title?: string) => Promise<string | null>
    warn?: (title: string, message: string, primaryLabel?: string) => Promise<boolean>
    form?: (opts: { title: string; fields: unknown[]; primaryLabel?: string; size?: string }) => Promise<Record<string, unknown> | null>
    showProgress?: (title: string, count: number, total: number, description?: string) => void
  } = {}
): GruntProxy {
  return {
    async call(opts) {
      try {
        const { data } = await client.post(`/api/v1/method/${opts.method}`, opts.args ?? {})
        return data?.data
      } catch (err: unknown) {
        const e = err as { response?: { data?: { detail?: string } } }
        const detail = e?.response?.data?.detail
        throw new Error(detail || 'Server error')
      }
    },

    throw(msg: string): never {
      throw new Error(msg)
    },

    async confirm(msg: string, title?: string) {
      if (callbacks.confirm) {
        return callbacks.confirm(msg, title)
      }
      return window.confirm(msg)
    },

    async msgprint(msgOrOpts: string | { message: string; title?: string; indicator?: string }) {
      if (callbacks.msgprint) {
        return callbacks.msgprint(msgOrOpts)
      }
      const text = typeof msgOrOpts === 'string' ? msgOrOpts : msgOrOpts.message
      alert(text)
    },

    show_alert(msg: string, type?: 'success' | 'error' | 'info' | 'warning') {
      if (callbacks.showAlert) {
        callbacks.showAlert(msg, type)
      }
    },

    async prompt(labelOrOpts, title?) {
      if (callbacks.prompt) {
        return callbacks.prompt(labelOrOpts, title)
      }
      const label = typeof labelOrOpts === 'string' ? labelOrOpts : labelOrOpts.label
      return window.prompt(label) ?? null
    },

    async warn(title: string, message: string, primaryLabel?: string) {
      if (callbacks.warn) {
        return callbacks.warn(title, message, primaryLabel)
      }
      return window.confirm(`${title}\n${message}`)
    },

    async form(opts) {
      if (callbacks.form) {
        return callbacks.form(opts)
      }
      return null
    },

    show_progress(title: string, count: number, total: number, description?: string) {
      callbacks.showProgress?.(title, count, total, description)
    },
  }
}

// ── Execution ────────────────────────────────────────────────────────────

/**
 * Execute all client scripts for a DocType, filtering by event.
 *
 * Scripts should define handler functions matching the event name:
 * ```js
 * function on_load(frm) { ... }
 * function validate(frm) { return true; }
 * function on_change(frm, fieldname) { ... }
 * ```
 *
 * Returns false if any validate handler returns false.
 */
export async function executeClientScripts(
  doctype: string,
  event: ClientScriptEvent,
  frm: FormProxy,
  gruntProxy: GruntProxy,
  changedField?: string
): Promise<boolean> {
  const scripts = await loadClientScripts(doctype)
  if (!scripts.length) return true

  for (const entry of scripts) {
    try {
      // Create a function scope with cur_frm and grunt
      const fn = new Function(
        'cur_frm',
        'frm',
        'grunt',
        'frappe',
        `${entry.script};\n` +
        `if (typeof ${event} === 'function') {\n` +
        `  return ${event}(cur_frm${event === 'on_change' ? `, '${changedField ?? ''}'` : ''});\n` +
        `}`
      )

      const result = await fn(frm, frm, gruntProxy, gruntProxy)

      // For validate event, false = cancel
      if (event === 'validate' && result === false) {
        return false
      }
    } catch (err) {
      console.warn(`[ClientScript] Error in "${entry.name}" (${event}):`, err)
    }
  }

  return true
}
