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

/** Handle returned by listview.add_button — allows in-place updates. */
export interface ScriptButtonHandle {
  update: (updates: { label?: string; variant?: string }) => void
}

/** Callback registered via frm.set_query — returns filters for a link field. */
export type LinkQueryFn = (
  doc: Record<string, unknown>,
) => { filters: Record<string, string> } | Record<string, string>

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
  /**
   * Register a dynamic filter for a Link field.
   *
   * ```js
   * frm.set_query('customer', function(doc) {
   *   return { filters: { company: doc.company, status: 'Active' } }
   * })
   * ```
   */
  set_query: (fieldname: string, fn: LinkQueryFn) => void
  refresh_field: (fieldname: string) => void
  add_button: (label: string, action: () => void | Promise<void>, options?: { variant?: string }) => void
  reload: () => Promise<void>
  save: () => Promise<void>
  /** Internal state modified by scripts */
  _display: Record<string, boolean>
  _reqd: Record<string, boolean>
  _df_props: Record<string, Record<string, unknown>>
  _queries: Record<string, LinkQueryFn>
}

/** Handle returned by listview.add_menu_item — allows in-place updates. */
export interface ScriptMenuItemHandle {
  update: (updates: { label?: string }) => void
  remove: () => void
}

/** ListView proxy exposed to client scripts as `listview` in `setup_list`. */
export interface ListViewProxy {
  doctype: string
  /** Add a custom button to the ListView toolbar. Returns a handle to update it later. */
  add_button: (label: string, action: () => void | Promise<void>, options?: { variant?: string }) => ScriptButtonHandle
  /** Add an item to the "⋯" header dropdown menu. Returns a handle to update or remove it. */
  add_menu_item: (label: string, action: () => void | Promise<void>, options?: { separator_before?: boolean }) => ScriptMenuItemHandle
  /** Reload the list data. */
  refresh: () => void
  /**
   * Replace the active filter set.
   *
   * ```js
   * listview.set_filters([{ fieldname: 'language', op: '=', value: 'uk', label: 'Мова' }])
   * ```
   */
  set_filters: (filters: Array<{ fieldname: string; op: string; value: string; label?: string; fieldtype?: string }>) => void
}

/** Framework helpers exposed as `grunt`. */
export interface GruntProxy {
  call: (opts: { method: string; args?: Record<string, unknown> }) => Promise<unknown>
  /** Raw HTTP helpers for arbitrary API calls. */
  api: {
    get: (url: string, params?: Record<string, unknown>) => Promise<unknown>
    post: (url: string, data?: unknown) => Promise<unknown>
    put: (url: string, data?: unknown) => Promise<unknown>
    delete: (url: string) => Promise<unknown>
  }
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
      `/api/v1/method/grunt.api.v1.scripting.get_client_scripts?doctype=${encodeURIComponent(doctype)}`
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
    reload?: () => Promise<void>
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
    _queries: {},

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

    set_query(fieldname: string, fn: LinkQueryFn) {
      proxy._queries[fieldname] = fn
    },

    refresh_field(fieldname: string) {
      callbacks.refreshField?.(fieldname)
    },

    add_button(label: string, action: () => void | Promise<void>, options?: { variant?: string }) {
      callbacks.addButton?.(label, action, options)
    },

    async reload() {
      await callbacks.reload?.()
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

    api: {
      async get(url: string, params?: Record<string, unknown>) {
        const { data } = await client.get(url, { params })
        return data
      },
      async post(url: string, body?: unknown) {
        const { data } = await client.post(url, body)
        return data
      },
      async put(url: string, body?: unknown) {
        const { data } = await client.put(url, body)
        return data
      },
      async delete(url: string) {
        const { data } = await client.delete(url)
        return data
      },
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

// ── ListView setup ────────────────────────────────────────────────────────

/**
 * Create a ListView proxy for client scripts.
 */
export function createListViewProxy(
  doctype: string,
  callbacks: {
    addButton?: (label: string, action: () => void | Promise<void>, options?: { variant?: string }) => ScriptButtonHandle
    addMenuItem?: (label: string, action: () => void | Promise<void>, options?: { separator_before?: boolean }) => ScriptMenuItemHandle
    refresh?: () => void
    setFilters?: (filters: Array<{ fieldname: string; op: string; value: string; label?: string; fieldtype?: string }>) => void
  } = {},
): ListViewProxy {
  return {
    doctype,
    add_button(label, action, options): ScriptButtonHandle {
      return callbacks.addButton?.(label, action, options) ?? { update: () => { } }
    },
    add_menu_item(label, action, options): ScriptMenuItemHandle {
      return callbacks.addMenuItem?.(label, action, options) ?? { update: () => { }, remove: () => { } }
    },
    refresh() {
      callbacks.refresh?.()
    },
    set_filters(filters) {
      callbacks.setFilters?.(filters)
    },
  }
}

/**
 * Execute `setup_list(listview)` from all client scripts for a DocType.
 *
 * Call once when the ListView mounts.
 */
export async function executeListSetup(
  doctype: string,
  listview: ListViewProxy,
  gruntProxy: GruntProxy,
): Promise<void> {
  const scripts = await loadClientScripts(doctype)
  if (!scripts.length) return

  for (const entry of scripts) {
    try {
      const fn = new Function(
        'listview',
        'grunt',
        'frappe',
        `${entry.script};\n` +
        `if (typeof setup_list === 'function') { return setup_list(listview); }`,
      )
      await fn(listview, gruntProxy, gruntProxy)
    } catch (err) {
      console.warn(`[ClientScript] Error in "${entry.name}" (setup_list):`, err)
    }
  }
}
