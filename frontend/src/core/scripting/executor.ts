/**
 * Client Script executor - runs user-defined JS in the form context.
 *
 * Client scripts are fetched from the backend per DocType and executed
 * within a controlled scope providing form helpers.
 *
 * Available in scripts:
 * - `cur_frm` / `frm` - current form proxy (get_value, set_value, add_button, etc.)
 * - `grunt` - framework helpers (call, throw, confirm, msgprint, show_alert)
 */

import client from '@/core/api/client'
import { useAuthStore } from '@/stores/auth'
import { grunt as appGrunt } from '@/core/grunt'
import { appUrl } from '@/core/workspaceUrl'
import type { DialogSize } from '@/core/composables/useDialog'
import type { ActionsApi } from '@/core/actions'
import { i18n, N_ } from '@/plugins/i18n'
import type { DocPerms } from '@/core/permissions'

// Types

/** Callback registered via frm.set_query - returns filters for a link field. */
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
  /**
   * Buttons and menu items of this form - see core/actions.ts. The standard
   * ones (save, duplicate, rename, delete, print, …) come from the framework's
   * `global_form.js`; change or remove them by id.
   *
   * ```js
   * frm.actions.add({ id: 'approve', label: 'Погодити', action: (frm) => ... })
   * frm.actions.remove('duplicate')
   * ```
   */
  actions: ActionsApi<FormProxy>
  /** What the user may do with this document (the server's `__perms`). */
  readonly perm: DocPerms
  /** The document's name, or null while it is new. */
  readonly name: string | null
  readonly is_dirty: boolean
  readonly is_saving: boolean
  readonly is_loading: boolean
  /** The form has at least one field the user can type into. */
  readonly has_editable_fields: boolean
  /** Ask for confirmation, then delete the document. */
  delete: () => void
  /** Open a copy of this document as a new one. */
  duplicate: () => void
  /** Throw away unsaved changes. */
  discard: () => void
  /** The rename dialog. */
  rename: () => void
  /** The public-link dialog. */
  share: () => void
  /** The related-documents dialog. */
  show_links: () => void
  /** Show/hide the activity timeline. */
  toggle_activity: () => void
  /** Open a print of this document: `html` (optionally auto-printing), `pdf` or `xlsx`. */
  print: (format?: string, options?: { autoprint?: boolean }) => void
  /** Workflow transitions the user may apply now (see the `on_transitions` event). */
  readonly transitions: WorkflowTransition[]
  /** Apply a workflow transition - asks for its prompt fields first, then reloads the document. */
  apply_transition: (action: string) => Promise<void>
  get_selected: () => Record<string, string[]>
  /** Re-fetch the document from the server; with `{ meta: true }` also the DocType definition. */
  reload: (options?: { meta?: boolean }) => Promise<void>
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
  /** undefined -> script left the sidebar decision to config */
  _sidebar_hidden?: boolean
}

/** An exporter offered in a list's menu (core/exporters). */
export interface ListExporterInfo {
  id: string
  label: string
}

/** ListView proxy exposed to client scripts as `listview` in `setup_list`. */
export interface ListViewProxy {
  doctype: string
  /**
   * Buttons and menu items of this list - see core/actions.ts. The standard
   * ones («Додати», refresh, export, bulk edit/delete…) come from the
   * framework's `global_list.js`; change or remove them by id.
   *
   * ```js
   * function setup_list(listview) {
   *   listview.actions.remove('add')
   *   listview.actions.add({ id: 'import', label: 'Імпорт', action: () => ... })
   * }
   * ```
   */
  actions: ActionsApi<ListViewProxy>
  /** Role-level rights on this DocType (the server still checks every document). */
  readonly perm: DocPerms
  /** Names of the selected rows. */
  readonly selected: string[]
  /** «Select all N» is on - the selection is every row matching the filters. */
  readonly all_selected: boolean
  readonly is_fetching: boolean
  /** Registered exporters (CSV, Excel…) - usable when `can_export`. */
  readonly exporters: ListExporterInfo[]
  /** The current view can be exported. */
  readonly can_export: boolean
  /** The active filters (the tree panel's node is one of them, e.g. `folder = …`). */
  readonly filters: ReadonlyArray<{ fieldname: string; op: string; value: string }>
  /** Re-fetch the rows; with `{ meta: true }` also the DocType definition. */
  refresh: (options?: { meta?: boolean }) => void
  /** Create a document (quick entry when the DocType has it). */
  new_doc: () => void
  /** The bulk «set a field» dialog for the selection. */
  bulk_edit: () => void
  /** Delete the selection (with the impact dialog). */
  bulk_delete: () => void
  /** Delete every matching row without per-document hooks (System Manager). */
  fast_delete: () => void
  export: (exporterId: string) => void
  customize_quick_filters: () => void
  /** Open the report builder for this DocType. */
  create_report: () => void
  /**
   * Replace the active filter set.
   *
   * ```js
   * listview.set_filters([{ fieldname: 'language', op: '=', value: 'uk', label: 'Мова' }])
   * ```
   */
  set_filters: (filters: Array<{ fieldname: string; op: string; value: string; label?: string; fieldtype?: string; displayValue?: string }>) => void
  /** Set a single quick-filter value by its id. */
  set_quick_filter_value: (id: string, value: string) => void
  /** Replace all quick-filter values at once. */
  set_quick_filters: (values: Record<string, string>) => void
  /**
   * Set it to accept files dragged in from the desktop - onto the list or onto
   * a node of the tree panel (`target` is that node, else `null`).
   *
   * ```js
   * listview.drop_files = (lv, files, target) => grunt.upload_files({ files, folder: target })
   * ```
   */
  drop_files?: (listview: ListViewProxy, files: File[], target: string | null) => unknown
}

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
    /** False for accounts provisioned via OIDC / email link that never set a password. */
    has_password: boolean
    /** Set (with the impersonator) while a System Manager is viewing as this user. */
    impersonated_by: { email: string; full_name: string } | null
  }
  /**
   * System Manager only: open a short-lived session as another user to verify
   * their access, then reload the app. Return to your own account from the
   * banner at the top of the screen. Rejects for non-System-Managers.
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
   * Let the user pick files and upload them as File records (with progress).
   * Resolves with the uploaded files - empty when cancelled.
   *
   * `choose_folder` asks where to put them (`folder` is the preselected one,
   * else «My files»); `files` skips the picker (e.g. files dropped in).
   *
   * ```js
   * const files = await grunt.upload_files({ folder: 'a1b2c3', choose_folder: true })
   * ```
   */
  upload_files: (opts?: {
    multiple?: boolean
    accept?: string
    files?: File[]
    choose_folder?: boolean
    folder?: string | null
    attached_to_doctype?: string
    attached_to_id?: string
    is_public?: boolean
  }) => Promise<import('@/core/api/files').FileItem[]>
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
  /**
   * Browser health checks for the «Стан системи» report - service worker,
   * offline cache and queue, network, storage (core/browserHealth.ts).
   */
  health: {
    diagnose_browser: () => Promise<import('@/core/browserHealth').HealthRow[]>
    persist_storage: () => Promise<boolean>
  }
}

/**
 * `on_transitions(frm)` runs whenever the workflow transitions allowed for the
 * document (re)load - `frm.transitions` holds them; global_form.js registers
 * them as `workflow:<action>` actions.
 */
export type ClientScriptEvent = 'on_load' | 'on_change' | 'validate' | 'before_save' | 'after_save' | 'on_transitions'

interface ClientScriptEntry {
  name: string
  script: string
}

/** Cache: doctype -> scripts. The pending request is cached too, so callers
 * that open a form at the same time (on_load, list setup…) share one fetch. */
const scriptCache = new Map<string, Promise<ClientScriptEntry[]>>()

// Script loading

/**
 * Fetch client scripts for a DocType from the backend.
 */
export function loadClientScripts(doctype: string): Promise<ClientScriptEntry[]> {
  let scripts = scriptCache.get(doctype)
  if (!scripts) {
    scripts = client
      .get<{ data: ClientScriptEntry[] }>(
        `/api/v1/method/grunt.api.v1.scripting.get_client_scripts?doctype=${encodeURIComponent(doctype)}`
      )
      .then(({ data }) => data?.data ?? [])
      .catch(() => {
        scriptCache.delete(doctype) // don't pin a failed fetch - retry next time
        return []
      })
    scriptCache.set(doctype, scripts)
  }
  return scripts
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

// Proxy factories

/**
 * Create a FormProxy from current form state.
 */
export interface WorkflowTransition {
  action: string
  to_state: string
  prompt_fields: string[]
  require_comment?: boolean
}

export interface FormProxyState {
  perm: DocPerms
  transitions: WorkflowTransition[]
  isDirty: boolean
  isSaving: boolean
  isLoading: boolean
  hasEditableFields: boolean
}

export interface FormProxyUi {
  delete: () => void
  duplicate: () => void
  discard: () => void
  rename: () => void
  share: () => void
  showLinks: () => void
  toggleActivity: () => void
  applyTransition: (action: string) => Promise<void>
}

export function createFormProxy(
  doctype: string,
  doc: Record<string, unknown>,
  fields: Record<string, unknown>[],
  callbacks: {
    setValue?: (field: string, value: unknown) => void
    refreshField?: (field: string) => void
    reload?: (options?: { meta?: boolean }) => Promise<void>
    save?: () => Promise<void>
    markClean?: () => void
    /** Live form state behind frm.perm / is_dirty / … (read on every access, so reactive). */
    state?: () => FormProxyState
    ui?: Partial<FormProxyUi>
  } = {},
  isNew: boolean = false,
  actions: ActionsApi<FormProxy> = NO_ACTIONS,
): FormProxy {
  const state = (): FormProxyState =>
    callbacks.state?.() ?? {
      perm: { write: true, delete: false, create: false },
      transitions: [],
      isDirty: false,
      isSaving: false,
      isLoading: false,
      hasEditableFields: true,
    }

  const proxy = {
    doctype,
    doc,
    fields,
    is_new: isNew,
    actions,
    _display: {},
    _reqd: {},
    _df_props: {},
    _queries: {},
    _selected_rows: {},

    get perm() { return state().perm },
    get name() { return proxy.is_new ? null : ((proxy.doc.name as string | undefined) ?? null) },
    get is_dirty() { return state().isDirty },
    get is_saving() { return state().isSaving },
    get is_loading() { return state().isLoading },
    get has_editable_fields() { return state().hasEditableFields },
    get transitions() { return state().transitions },

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

    delete() { callbacks.ui?.delete?.() },
    duplicate() { callbacks.ui?.duplicate?.() },
    discard() { callbacks.ui?.discard?.() },
    rename() { callbacks.ui?.rename?.() },
    share() { callbacks.ui?.share?.() },
    show_links() { callbacks.ui?.showLinks?.() },
    toggle_activity() { callbacks.ui?.toggleActivity?.() },
    async apply_transition(action: string) { await callbacks.ui?.applyTransition?.(action) },

    print(format = 'html', options: { autoprint?: boolean } = {}) {
      const name = proxy.name
      if (!name) return
      const params = new URLSearchParams({ doctype, doc_id: name, fmt: format })
      if (options.autoprint) params.set('autoprint', '1')
      const token = localStorage.getItem('grunt_token')
      if (token) params.set('token', token)
      window.open(`/api/v1/method/grunt.document.base.Document.print?${params}`, '_blank', 'noopener')
    },

    get_selected() {
      return Object.fromEntries(
        Object.entries(proxy._selected_rows)
          .filter(([, rows]) => Array.isArray(rows) && rows.length > 0)
          .map(([fieldname, rows]) => [fieldname, [...rows]]),
      )
    },

    async reload(options?: { meta?: boolean }) {
      await callbacks.reload?.(options)
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
  } as FormProxy

  return proxy
}

/** Placeholder until a registry is attached (tests, detached proxies). */
const NO_ACTIONS: ActionsApi<any> = {
  add: () => {},
  update: () => {},
  remove: () => {},
  get: () => undefined,
  list: () => [],
  run: async () => {},
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

  // `{ status: 'Open', date__gt: … }` -> list-URL query `filter[status__eq]=Open&…`.
  const listQuery = (filters?: Record<string, unknown> | null): Record<string, unknown> =>
    Object.fromEntries(
      Object.entries(filters ?? {}).map(([key, val]) => [`filter[${key.includes('__') ? key : `${key}__eq`}]`, val]),
    )

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
    const workspace = currentWorkspace()
    const [kind, ...rest] = routeParts
    const lowerKind = kind.toLowerCase()

    if (lowerKind === 'list') {
      return rest[0] ? appUrl({ name: rest[0], workspace, query: listQuery(filters) }) : null
    }
    if (lowerKind === 'form') {
      const [doctype, docId] = rest
      if (!doctype) return null
      if (!docId || docId.toLowerCase() === 'new') {
        return appUrl({ name: doctype, id: 'new', workspace, query: filters })
      }
      return appUrl({ name: doctype, id: docId, workspace })
    }
    if (lowerKind === 'report') {
      return rest[0] ? appUrl({ type: 'Report', name: rest[0], workspace }) : null
    }
    if (routeParts.length === 1) {
      return appUrl({ name: kind, workspace, query: listQuery(filters) })
    }
    return appUrl({ name: routeParts[0], id: routeParts[1], workspace })
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

  return {
    get session() {
      const u = useAuthStore().user
      return {
        user: u?.email ?? 'guest@grunt.local',
        full_name: u?.full_name ?? 'Guest',
        roles: u?.roles ?? [],
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

    async upload_files(opts = {}) {
      const picked = opts.files?.length ? opts.files : await pickFiles(opts.multiple ?? true, opts.accept)
      if (!picked.length) return []
      const { filesApi } = await import('@/core/api/files')
      let folder = opts.folder ?? undefined
      if (opts.choose_folder) {
        const { useFolderPicker } = await import('@/core/composables/useFolderPicker')
        const chosen = await useFolderPicker().pick({ files: picked, folder })
        if (!chosen) return []
        folder = chosen
      }
      const uploaded: import('@/core/api/files').FileItem[] = []
      for (const [i, file] of picked.entries()) {
        if (picked.length > 1) {
          this.show_progress(translate(N_('Uploading files')), i, picked.length, file.name)
        }
        try {
          uploaded.push(
            await filesApi.upload(file, {
              attachedToDoctype: opts.attached_to_doctype,
              attachedToId: opts.attached_to_id,
              folder,
              isPublic: opts.is_public,
            }),
          )
        } catch (err) {
          const detail = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          this.show_alert(`${file.name}: ${detail ?? translate(N_('Upload failed'))}`, 'error')
        }
      }
      if (picked.length > 1) {
        this.show_progress(translate(N_('Uploading files')), picked.length, picked.length)
      }
      return uploaded
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


    passkey: {
      isSupported() {
        return typeof window !== 'undefined' && !!window.PublicKeyCredential
      },
      async register(label?: string, opts?: { mode?: 'cross-device' }) {
        const { authApi } = await import('@/core/api/auth')
        const { createPasskey, isWebAuthnSupported } = await import('@/core/composables/useWebAuthn')
        if (!isWebAuthnSupported()) throw new Error(i18n.global.t('This browser does not support passkeys'))
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

    health: appGrunt.health,
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

/** Open the browser's file picker; resolves with the chosen files ([] on cancel). */
function pickFiles(multiple: boolean, accept?: string): Promise<File[]> {
  return new Promise((resolve) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.multiple = multiple
    if (accept) input.accept = accept
    input.addEventListener('change', () => resolve(Array.from(input.files ?? [])))
    input.addEventListener('cancel', () => resolve([]))
    input.click()
  })
}

/** `__('text')` in client scripts - the UI translation (and an extraction marker). */
function translate(text: string, params?: Record<string, unknown>): string {
  // With params vue-i18n fills `{n}` itself; the replace covers an untranslated key.
  if (!params) return i18n.global.t(text)
  let out = i18n.global.t(text, params)
  for (const [k, v] of Object.entries(params)) out = out.replaceAll(`{${k}}`, String(v))
  return out
}

// Execution

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
        '__',
        `${entry.script};\n` +
        `if (typeof ${event} === 'function') {\n` +
        `  return ${event}(cur_frm${event === 'on_change' ? `, '${changedField ?? ''}'` : ''});\n` +
        `}`
      )

      const result = await fn(frm, frm, gruntProxy, translate)

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

// ListView setup

/**
 * Create a ListView proxy for client scripts.
 */
export interface ListViewState {
  perm: DocPerms
  selected: string[]
  allSelected: boolean
  isFetching: boolean
  exporters: ListExporterInfo[]
  canExport: boolean
  filters: Array<{ fieldname: string; op: string; value: string }>
}

export function createListViewProxy(
  doctype: string,
  callbacks: {
    state?: () => ListViewState
    refresh?: (options?: { meta?: boolean }) => void
    newDoc?: () => void
    bulkEdit?: () => void
    bulkDelete?: () => void
    fastDelete?: () => void
    exportWith?: (exporterId: string) => void
    customizeQuickFilters?: () => void
    createReport?: () => void
    setFilters?: (filters: Array<{ fieldname: string; op: string; value: string; label?: string; fieldtype?: string; displayValue?: string }>) => void
    setQuickFilterValue?: (id: string, value: string) => void
    setQuickFilters?: (values: Record<string, string>) => void
  } = {},
  actions: ActionsApi<ListViewProxy> = NO_ACTIONS,
): ListViewProxy {
  const state = (): ListViewState =>
    callbacks.state?.() ?? {
      perm: { write: false, delete: false, create: false },
      selected: [],
      allSelected: false,
      isFetching: false,
      exporters: [],
      canExport: false,
      filters: [],
    }
  return {
    doctype,
    actions,
    get perm() { return state().perm },
    get selected() { return state().selected },
    get all_selected() { return state().allSelected },
    get is_fetching() { return state().isFetching },
    get exporters() { return state().exporters },
    get can_export() { return state().canExport },
    get filters() { return state().filters },
    refresh(options) { callbacks.refresh?.(options) },
    new_doc() { callbacks.newDoc?.() },
    bulk_edit() { callbacks.bulkEdit?.() },
    bulk_delete() { callbacks.bulkDelete?.() },
    fast_delete() { callbacks.fastDelete?.() },
    export(exporterId) { callbacks.exportWith?.(exporterId) },
    customize_quick_filters() { callbacks.customizeQuickFilters?.() },
    create_report() { callbacks.createReport?.() },
    set_filters(filters) { callbacks.setFilters?.(filters) },
    set_quick_filter_value(id, value) { callbacks.setQuickFilterValue?.(id, value) },
    set_quick_filters(values) { callbacks.setQuickFilters?.(values) },
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
        '__',
        `${entry.script};\n` +
        `if (typeof setup_list === 'function') { return setup_list(listview); }`,
      )
      await fn(listview, gruntProxy, translate)
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
        '__',
        `${entry.script};\n` +
        `if (typeof on_quick_filter_change === 'function') { return on_quick_filter_change(listview, change); }`,
      )
      await fn(listview, gruntProxy, change, translate)
    } catch (err) {
      console.warn(`[ClientScript] Error in "${entry.name}" (on_quick_filter_change):`, err)
    }
  }
}
