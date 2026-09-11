/**
 * Client Script executor — runs user-defined JS in the form context.
 *
 * Client scripts are fetched from the backend per DocType and executed
 * within a controlled scope providing form helpers.
 *
 * Available in scripts:
 * - `cur_frm` / `frm` — current form proxy (get_value, set_value, add_button, etc.)
 * - `grunt` — framework helpers (call, throw, confirm, msgprint, show_alert)
 */

import client from '@/core/api/client'
import { useAuthStore } from '@/stores/auth'
import type { DialogSize } from '@/core/composables/useDialog'

// ── Types ────────────────────────────────────────────────────────────────

export interface ScriptButton {
  label: string
  action: () => void | Promise<void>
  severity?: string
  className?: string
  icon?: string
  group?: string
}

export interface ScriptButtonOptions {
  variant?: string
  color?: string
  icon?: string
  group?: string
}

export interface ScriptMenuItem {
  label: string
  action: () => void | Promise<void>
  icon?: string
  separator_before?: boolean
}

export interface ScriptMenuItemOptions {
  separator_before?: boolean
  icon?: string
}

/** Handle returned by frm.add_menu_item — allows in-place updates/removal. */
export interface FormScriptMenuItemHandle {
  update: (updates: { label?: string; icon?: string; separator_before?: boolean }) => void
  remove: () => void
}

/** Handle returned by listview.add_button — allows in-place updates. */
export interface ScriptButtonHandle {
  update: (updates: { label?: string; severity?: string }) => void
}

/** Callback registered via frm.set_query — returns filters for a link field. */
export type LinkQueryFn = (
  doc: Record<string, unknown>,
) => { filters: Record<string, string | string[]> } | Record<string, string | string[]>

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
  add_button: (label: string, action: () => void | Promise<void>, options?: ScriptButtonOptions) => void
  add_custom_button: (
    label: string,
    action: () => void | Promise<void>,
    group?: string,
    options?: ScriptButtonOptions,
  ) => void
  add_menu_item: (
    label: string,
    action: () => void | Promise<void>,
    options?: ScriptMenuItemOptions,
  ) => FormScriptMenuItemHandle
  remove_custom_button: (label: string, group?: string | null) => void
  clear_custom_buttons: () => void
  change_custom_button_type: (label: string, group: string | null, buttonType: string) => void
  get_selected: () => Record<string, string[]>
  reload: () => Promise<void>
  save: () => Promise<void>
  /** Reset the dirty-state baseline to the current form values (for display-only set_value calls). */
  mark_clean: () => void
  /**
   * Show/hide the document detail sidebar. Overrides the DocType's
   * `form_show_sidebar` for this form. Call from `refresh`/`onload`.
   */
  toggle_sidebar: (show: boolean) => void
  hide_sidebar: () => void
  show_sidebar: () => void
  /** Internal state modified by scripts */
  _display: Record<string, boolean>
  _reqd: Record<string, boolean>
  _df_props: Record<string, Record<string, unknown>>
  _queries: Record<string, LinkQueryFn>
  _selected_rows: Record<string, string[]>
  /** undefined → script left the sidebar decision to config */
  _sidebar_hidden?: boolean
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
  set_filters: (filters: Array<{ fieldname: string; op: string; value: string; label?: string; fieldtype?: string }>) => void  /** Set a single quick-filter value by its id. */
  set_quick_filter_value: (id: string, value: string) => void
  /** Replace all quick-filter values at once. */
  set_quick_filters: (values: Record<string, string>) => void}

export interface ListQuickFilterChange {
  id: string
  value: string
  previousValue: string
  fieldname?: string
  operator?: string
  source?: string
  viewScope?: 'list' | 'tree'
}

/** Framework helpers exposed as `grunt`. */
export interface GruntProxy {
  /** The currently signed-in user (read-only snapshot). */
  session: {
    user: string
    full_name: string
    roles: string[]
    is_superadmin: boolean
    /** False for accounts provisioned via OIDC / email link that never set a password. */
    has_password: boolean
    /** Set (with the impersonator) while a superadmin is viewing as this user. */
    impersonated_by: { email: string; full_name: string } | null
  }
  /**
   * Superadmin only: open a short-lived session as another user to verify
   * their access, then reload the app. Return to your own account from the
   * banner at the top of the screen. Rejects for non-superadmins.
   */
  impersonate: (userId: string) => Promise<void>
  /**
   * Call a whitelisted server method.
   *
   * Both signatures are supported:
   * ```js
   * // Positional
   * grunt.call('hrm.hrm.api.get_positions_by_department', { department: doc.department })
   *
   * // Object-style
   * grunt.call({ method: 'hrm.hrm.api.get_positions_by_department', args: { department: doc.department } })
   * ```
   */
  call: {
    (method: string, args?: Record<string, unknown>): Promise<unknown>
    (opts: { method: string; args?: Record<string, unknown> }): Promise<unknown>
  }
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
  form: (opts: { title: string; fields: unknown[]; primaryLabel?: string; size?: DialogSize; buttons?: unknown[] }) => Promise<Record<string, unknown> | null>
  /** Selectable list/table dialog. Resolves with picked row(s) or null. */
  select: (opts: {
    title: string
    columns: { key: string; label: string; width?: string; align?: 'left' | 'right' | 'center' }[]
    rows: Record<string, unknown>[]
    rowKey?: string
    multiple?: boolean
    searchable?: boolean
    primaryLabel?: string
    size?: DialogSize
    description?: string
    maxHeight?: string
    fields?: unknown[]
    buttons?: unknown[]
  }) => Promise<Record<string, unknown>[] | Record<string, unknown> | null>
  show_progress: (title: string, count: number, total: number, description?: string) => void
  /**
   * Subscribe to a WebSocket event on the current document channel.
   * Returns an unsubscribe function.
   *
   * ```js
   * const off = grunt.onMessage('import_progress', (data) => {
   *   console.log(data.processed, data.total)
   * })
   * // later: off()
   * ```
   */
  onMessage: (event: string, cb: (data: unknown) => void) => () => void
  /**
   * Subscribe to progress updates published via `self.publish_progress()` in Python.
   * Returns an unsubscribe function.
   *
   * ```js
   * const off = grunt.on_progress(({ processed, total, message }) => {
   *   console.log(`${processed} / ${total}`)
   * })
   * ```
   */
  on_progress: (cb: (data: { processed: number; total: number; message?: string }) => void) => () => void
  route_options?: Record<string, unknown> | null
  set_route: (...route: unknown[]) => void
  open_route: (...route: unknown[]) => void
  ui: {
    form: {
      add_standard_menu_items: (frm: FormProxy) => void
    }
  }
  /**
   * WebAuthn / passkey helpers (drive `/api/v1/auth/webauthn/*` from a client
   * script). `mode: 'cross-device'` registers/uses a passkey that lives on a
   * phone (QR / Bluetooth).
   *
   * ```js
   * const { label } = await grunt.passkey.register('iPhone', { mode: 'cross-device' })
   * ```
   */
  passkey: {
    isSupported: () => boolean
    register: (label?: string, opts?: { mode?: 'cross-device' }) => Promise<{ name: string; label: string }>
    list: () => Promise<Array<{ name: string; label: string; last_used_at: string | null }>>
    rename: (name: string, label: string) => Promise<void>
    remove: (name: string) => Promise<void>
  }
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
    addButton?: (label: string, action: () => void | Promise<void>, options?: ScriptButtonOptions) => void
    addMenuItem?: (
      label: string,
      action: () => void | Promise<void>,
      options?: ScriptMenuItemOptions,
    ) => FormScriptMenuItemHandle
    removeButton?: (label: string, group?: string | null) => void
    clearButtons?: () => void
    updateButtonType?: (label: string, group: string | null, buttonType: string) => void
    reload?: () => Promise<void>
    save?: () => Promise<void>
    markClean?: () => void
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
    _selected_rows: {},

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

    add_button(label: string, action: () => void | Promise<void>, options?: ScriptButtonOptions) {
      callbacks.addButton?.(label, action, options)
    },

    add_custom_button(
      label: string,
      action: () => void | Promise<void>,
      group?: string,
      options?: ScriptButtonOptions,
    ) {
      const merged: ScriptButtonOptions = {
        ...(options ?? {}),
        group: options?.group ?? group,
      }
      callbacks.addButton?.(label, action, merged)
    },

    add_menu_item(
      label: string,
      action: () => void | Promise<void>,
      options?: ScriptMenuItemOptions,
    ): FormScriptMenuItemHandle {
      return callbacks.addMenuItem?.(label, action, options) ?? {
        update: () => {},
        remove: () => {},
      }
    },

    remove_custom_button(label: string, group?: string | null) {
      callbacks.removeButton?.(label, group)
    },

    clear_custom_buttons() {
      callbacks.clearButtons?.()
    },

    change_custom_button_type(label: string, group: string | null, buttonType: string) {
      callbacks.updateButtonType?.(label, group, buttonType)
    },

    get_selected() {
      return Object.fromEntries(
        Object.entries(proxy._selected_rows)
          .filter(([, rows]) => Array.isArray(rows) && rows.length > 0)
          .map(([fieldname, rows]) => [fieldname, [...rows]]),
      )
    },

    async reload() {
      await callbacks.reload?.()
    },

    async save() {
      await callbacks.save?.()
    },

    mark_clean() {
      callbacks.markClean?.()
    },

    toggle_sidebar(show: boolean) {
      proxy._sidebar_hidden = !show
    },

    hide_sidebar() {
      proxy._sidebar_hidden = true
    },

    show_sidebar() {
      proxy._sidebar_hidden = false
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
    form?: (opts: { title: string; fields: unknown[]; primaryLabel?: string; size?: DialogSize }) => Promise<Record<string, unknown> | null>
    select?: (opts: Record<string, unknown>) => Promise<unknown>
    showProgress?: (title: string, count: number, total: number, description?: string) => void
    navigateTo?: (href: string, inNewTab: boolean) => void
  } = {},
  // Internal registry populated by useClientScripts when a WS message arrives
  _messageListeners: Map<string, Set<(data: unknown) => void>> = new Map(),
): GruntProxy {
  const isPlainObject = (v: unknown): v is Record<string, unknown> =>
    typeof v === 'object' && v !== null && !Array.isArray(v)

  const currentWorkspace = (): string => {
    const parts = window.location.pathname.split('/').filter(Boolean)
    if (parts[0] === 'app' && parts[1]) return decodeURIComponent(parts[1])
    if (parts[0]) return decodeURIComponent(parts[0])
    return 'grunt'
  }

  const buildListQuery = (filters?: Record<string, unknown> | null): string => {
    if (!filters) return ''
    const params = new URLSearchParams()
    for (const [rawKey, rawVal] of Object.entries(filters)) {
      if (rawVal == null) continue
      const key = rawKey.includes('__') ? rawKey : `${rawKey}__eq`
      params.append(`filter[${key}]`, String(rawVal))
    }
    const q = params.toString()
    return q ? `?${q}` : ''
  }

  const buildQuery = (paramsObject?: Record<string, unknown> | null): string => {
    if (!paramsObject) return ''
    const params = new URLSearchParams()
    for (const [key, rawVal] of Object.entries(paramsObject)) {
      if (rawVal == null) continue
      params.append(key, String(rawVal))
    }
    const q = params.toString()
    return q ? `?${q}` : ''
  }

  const normalizeRouteParts = (route: unknown[]): string[] => {
    const parts = route.length === 1 && Array.isArray(route[0])
      ? route[0] as unknown[]
      : route
    return parts
      .map((v) => String(v ?? '').trim())
      .filter(Boolean)
  }

  const buildWorkspaceHref = (
    routeParts: string[],
    filters?: Record<string, unknown> | null,
  ): string | null => {
    if (!routeParts.length) return null
    const ws = encodeURIComponent(currentWorkspace())
    const [kind, ...rest] = routeParts
    const lowerKind = kind.toLowerCase()

    if (lowerKind === 'list') {
      const doctype = rest[0]
      if (!doctype) return null
      return `/app/${ws}/${encodeURIComponent(doctype)}${buildListQuery(filters)}`
    }

    if (lowerKind === 'form') {
      const doctype = rest[0]
      const docId = rest[1]
      if (!doctype) return null
      if (!docId || docId.toLowerCase() === 'new') {
        return `/app/${ws}/${encodeURIComponent(doctype)}/new${buildQuery(filters)}`
      }
      return `/app/${ws}/${encodeURIComponent(doctype)}/${encodeURIComponent(docId)}`
    }

    if (lowerKind === 'report') {
      const reportName = rest[0]
      if (!reportName) return null
      return `/app/${ws}/report/${encodeURIComponent(reportName)}`
    }

    if (routeParts.length === 1) {
      return `/app/${ws}/${encodeURIComponent(kind)}${buildListQuery(filters)}`
    }

    if (routeParts.length >= 2) {
      return `/app/${ws}/${encodeURIComponent(routeParts[0])}/${encodeURIComponent(routeParts[1])}`
    }

    return null
  }

  let routeOptions: Record<string, unknown> | null = null

  const resolveRouteCall = (route: unknown[]): { parts: string[]; filters: Record<string, unknown> | null } => {
    if (!route.length) return { parts: [], filters: routeOptions }
    const last = route[route.length - 1]
    const hasInlineFilters = isPlainObject(last)
    const rawParts = hasInlineFilters ? route.slice(0, -1) : route
    return {
      parts: normalizeRouteParts(rawParts),
      filters: (hasInlineFilters ? (last as Record<string, unknown>) : routeOptions) ?? null,
    }
  }

  const navigateRoute = (route: unknown[], inNewTab: boolean) => {
    const { parts, filters } = resolveRouteCall(route)
    const href = buildWorkspaceHref(parts, filters)
    if (!href) return
    if (callbacks.navigateTo) {
      try {
        callbacks.navigateTo(href, inNewTab)
        routeOptions = null
        return
      } catch {
        // Fall back to hard navigation when injected router navigation fails.
      }
    }
    if (inNewTab) window.open(href, '_blank')
    else window.location.assign(href)
    routeOptions = null
  }

  const addStandardFormMenuItems = (frm: FormProxy): void => {
    const documentName = String(frm.doc.name ?? '').trim()
    const openInNewTab = (url: string) => {
      window.open(url, '_blank', 'noopener')
    }

    if (documentName) {
      const printUrl = (format: string, autoPrint = false): string => {
        const params = new URLSearchParams({
          doctype: frm.doctype,
          doc_id: documentName,
          fmt: format,
        })
        if (autoPrint) params.set('autoprint', '1')
        const token = localStorage.getItem('grunt_token')
        if (token) params.set('token', token)
        return `/api/v1/method/grunt.document.base.Document.print?${params.toString()}`
      }

      frm.add_menu_item('Print', () => openInNewTab(printUrl('html', true)), { icon: 'printer' })
      frm.add_menu_item('Excel (.xlsx)', () => openInNewTab(printUrl('xlsx')), { icon: 'file-spreadsheet' })
      frm.add_menu_item('PDF', () => openInNewTab(printUrl('pdf')), { icon: 'file-text' })
      frm.add_menu_item('HTML', () => openInNewTab(printUrl('html')), { icon: 'globe' })
      frm.add_menu_item(
        'Open in new tab',
        () => openInNewTab(`/app/${encodeURIComponent(currentWorkspace())}/${encodeURIComponent(frm.doctype)}/${encodeURIComponent(documentName)}`),
        { icon: 'external-link' },
      )
    }

    const workspace = encodeURIComponent(currentWorkspace())
    frm.add_menu_item(
      'Edit DocType',
      () => openInNewTab(`/app/${workspace}/DocType/${encodeURIComponent(frm.doctype)}`),
      { icon: 'settings' },
    )
    frm.add_menu_item(
      'Configure print',
      () => openInNewTab(`/app/${workspace}/PrintFormat?filter%5Bdoctype%5D=${encodeURIComponent(frm.doctype)}`),
      { icon: 'sliders-horizontal' },
    )
  }

  return {
    get session() {
      const u = useAuthStore().user
      return {
        user: u?.email ?? 'guest@grunt.local',
        full_name: u?.full_name ?? 'Guest',
        roles: u?.roles ?? [],
        is_superadmin: !!u?.is_superadmin,
        has_password: u?.has_password ?? true,
        impersonated_by: useAuthStore().impersonatedBy,
      }
    },

    async impersonate(userId: string) {
      const auth = useAuthStore()
      await auth.startImpersonation(userId)
      // Full reload so every store re-initialises under the new identity.
      window.location.href = '/'
    },

    async call(methodOrOpts: string | { method: string; args?: Record<string, unknown> }, argsArg?: Record<string, unknown>) {
      const method = typeof methodOrOpts === 'string' ? methodOrOpts : methodOrOpts.method
      const args = typeof methodOrOpts === 'string' ? (argsArg ?? {}) : (methodOrOpts.args ?? {})
      try {
        const { data } = await client.post(`/api/v1/method/${method}`, args)
        return data?.data
      } catch (err: unknown) {
        const body = (err as { response?: { data?: Record<string, unknown> } })?.response?.data
        const errBody = body?.error as { message?: string } | string | undefined
        const message =
          (typeof errBody === 'object' ? errBody?.message : errBody) ??
          (body?.detail as string | undefined) ??
          (body?.message as string | undefined)
        throw new Error(typeof message === 'string' ? message : 'Server error')
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

    async select(opts) {
      if (callbacks.select) {
        return callbacks.select(opts as Record<string, unknown>) as any
      }
      return null
    },

    show_progress(title: string, count: number, total: number, description?: string) {
      callbacks.showProgress?.(title, count, total, description)
    },

    onMessage(event: string, cb: (data: unknown) => void): () => void {
      if (!_messageListeners.has(event)) {
        _messageListeners.set(event, new Set())
      }
      _messageListeners.get(event)!.add(cb)
      return () => _messageListeners.get(event)?.delete(cb)
    },

    on_progress(cb: (data: { processed: number; total: number; message?: string }) => void): () => void {
      return this.onMessage('import_progress', cb as (data: unknown) => void)
    },

    get route_options() {
      return routeOptions
    },

    set route_options(value: Record<string, unknown> | null | undefined) {
      routeOptions = isPlainObject(value) ? value : null
    },

    set_route(...route: unknown[]) {
      navigateRoute(route, false)
    },

    open_route(...route: unknown[]) {
      navigateRoute(route, true)
    },

    ui: {
      form: {
        add_standard_menu_items: addStandardFormMenuItems,
      },
    },

    passkey: {
      isSupported() {
        return typeof window !== 'undefined' && !!window.PublicKeyCredential
      },
      async register(label?: string, opts?: { mode?: 'cross-device' }) {
        const { authApi } = await import('@/core/api/auth')
        const { createPasskey, isWebAuthnSupported } = await import('@/core/composables/useWebAuthn')
        if (!isWebAuthnSupported()) throw new Error('Цей браузер не підтримує ключі доступу')
        const { options, challenge_token } = await authApi.enrollBegin(
          'webauthn',
          opts?.mode ? { mode: opts.mode } : {},
        )
        const credential = await createPasskey(options)
        return authApi.enrollComplete('webauthn', { challenge_token, response: credential, label })
      },
      async list() {
        const { authApi } = await import('@/core/api/auth')
        return authApi.listPasskeys()
      },
      async rename(name: string, label: string) {
        const { authApi } = await import('@/core/api/auth')
        await authApi.renamePasskey(name, label)
      },
      async remove(name: string) {
        const { authApi } = await import('@/core/api/auth')
        await authApi.deletePasskey(name)
      },
    },
  }
}

/** Dispatch a WS message to all listeners registered via grunt.onMessage. */
export function dispatchMessageToProxy(
  listeners: Map<string, Set<(data: unknown) => void>>,
  event: string,
  data: unknown,
): void {
  listeners.get(event)?.forEach(cb => {
    try { cb(data) } catch { /* ignore script errors */ }
  })
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
        `${entry.script};\n` +
        `if (typeof ${event} === 'function') {\n` +
        `  return ${event}(cur_frm${event === 'on_change' ? `, '${changedField ?? ''}'` : ''});\n` +
        `}`
      )

      const result = await fn(frm, frm, gruntProxy)

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
    setQuickFilterValue?: (id: string, value: string) => void
    setQuickFilters?: (values: Record<string, string>) => void
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
    set_quick_filter_value(id, value) {
      callbacks.setQuickFilterValue?.(id, value)
    },
    set_quick_filters(values) {
      callbacks.setQuickFilters?.(values)
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
        `${entry.script};\n` +
        `if (typeof setup_list === 'function') { return setup_list(listview); }`,
      )
      await fn(listview, gruntProxy)
    } catch (err) {
      console.warn(`[ClientScript] Error in "${entry.name}" (setup_list):`, err)
    }
  }
}

/**
 * Execute `on_quick_filter_change(listview, change)` from client scripts.
 *
 * Example in Client Script:
 *
 * ```js
 * function on_quick_filter_change(listview, change) {
 *   if (change.id !== 'as_of_date') return
 *   listview.set_quick_filter_value('valid_from_upto', change.value)
 * }
 * ```
 */
export async function executeListQuickFilterOnChange(
  doctype: string,
  listview: ListViewProxy,
  gruntProxy: GruntProxy,
  change: ListQuickFilterChange,
): Promise<void> {
  const scripts = await loadClientScripts(doctype)
  if (!scripts.length) return

  for (const entry of scripts) {
    try {
      const fn = new Function(
        'listview',
        'grunt',
        'change',
        `${entry.script};\n` +
        `if (typeof on_quick_filter_change === 'function') { return on_quick_filter_change(listview, change); }`,
      )
      await fn(listview, gruntProxy, change)
    } catch (err) {
      console.warn(`[ClientScript] Error in "${entry.name}" (on_quick_filter_change):`, err)
    }
  }
}
