/**
 * Client Script executor — runs user-defined JS in the form context.
 *
 * Client scripts are fetched from the backend per DocType and executed
 * within a controlled scope providing form helpers.
 *
 * Available in scripts:
 * - `cur_frm` — current form proxy (get_value, set_value, toggle_display, etc.)
 * - `grunt` — framework helpers (call, throw, confirm, msgprint)
 */

import { api } from '@/core/api/client'

/** Form proxy exposed to client scripts as `cur_frm`. */
export interface FormProxy {
  doctype: string
  doc: Record<string, unknown>
  fields: Record<string, unknown>[]
  get_value: (fieldname: string) => unknown
  set_value: (fieldname: string, value: unknown) => void
  toggle_display: (fieldname: string, show: boolean) => void
  toggle_reqd: (fieldname: string, reqd: boolean) => void
  set_df_property: (fieldname: string, prop: string, value: unknown) => void
  refresh_field: (fieldname: string) => void
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
  confirm: (msg: string) => Promise<boolean>
  msgprint: (msg: string) => void
}

export type ClientScriptEvent = 'on_load' | 'on_change' | 'validate' | 'before_save' | 'after_save'

interface ClientScriptEntry {
  name: string
  script: string
}

/** Cache: doctype -> scripts */
const scriptCache = new Map<string, ClientScriptEntry[]>()

/**
 * Fetch client scripts for a DocType from the backend.
 */
export async function loadClientScripts(doctype: string): Promise<ClientScriptEntry[]> {
  if (scriptCache.has(doctype)) {
    return scriptCache.get(doctype)!
  }

  try {
    const { data } = await api.get<{ data: ClientScriptEntry[] }>(
      `/client-script/${encodeURIComponent(doctype)}`
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
    save?: () => Promise<void>
  } = {}
): FormProxy {
  const proxy: FormProxy = {
    doctype,
    doc: { ...doc },
    fields,
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
    msgprint?: (msg: string) => void
    confirm?: (msg: string) => Promise<boolean>
  } = {}
): GruntProxy {
  return {
    async call(opts) {
      const { data } = await api.post(`/method/${opts.method}`, opts.args ?? {})
      return data?.data
    },

    throw(msg: string): never {
      throw new Error(msg)
    },

    async confirm(msg: string) {
      if (callbacks.confirm) {
        return callbacks.confirm(msg)
      }
      return window.confirm(msg)
    },

    msgprint(msg: string) {
      if (callbacks.msgprint) {
        callbacks.msgprint(msg)
      } else {
        alert(msg)
      }
    },
  }
}

/**
 * Execute all client scripts for a DocType, filtering by event.
 *
 * Scripts should define handler functions matching the event name:
 * ```js
 * function on_load(frm) { ... }
 * function validate(frm) { return true; }
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
        'grunt',
        'frappe',
        `${entry.script};\n` +
        `if (typeof ${event} === 'function') {\n` +
        `  return ${event}(cur_frm${event === 'on_change' ? `, '${changedField ?? ''}'` : ''});\n` +
        `}`
      )

      const result = fn(frm, gruntProxy, gruntProxy)

      // For validate event, false = cancel
      if (event === 'validate' && result === false) {
        return false
      }
    } catch (err) {
      console.error(`[ClientScript] Error in "${entry.name}" (${event}):`, err)
      if (event === 'validate') {
        return false
      }
    }
  }

  return true
}
