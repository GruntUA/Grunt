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
import type { ComponentDialogOptions, DialogSize } from '@/core/composables/useDialog'
import { appDialog } from '@/core/appDialogs'
import type { ActionsApi } from '@/core/actions'
import { i18n, N_ } from '@/plugins/i18n'
import type { DocType } from '@/types'
import { createFormDashboard, type FormDashboardApi } from '@/core/scripting/formDashboard'

// Types (the public client-script API lives in ./types)

import type {
  ClientScriptEvent,
  FormProxy,
  FormProxyState,
  FormProxyUi,
  GruntProxy,
  LinkQueryFn,
  ListQuickFilterChange,
  ListViewProxy,
  ListViewState,
} from '@/core/scripting/types'

export type {
  ClientScriptEvent,
  FormProxy,
  FormProxyState,
  FormProxyUi,
  GruntProxy,
  LinkQueryFn,
  ListExporterInfo,
  ListQuickFilterChange,
  ListViewProxy,
  ListViewState,
  WorkflowTransition,
} from '@/core/scripting/types'

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
    meta?: () => DocType | null
  } = {},
  isNew: boolean = false,
  actions: ActionsApi<FormProxy> = NO_ACTIONS,
  dashboard: FormDashboardApi = createFormDashboard(),
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
    dashboard,
    _display: {},
    _reqd: {},
    _df_props: {},
    _queries: {},
    _selected_rows: {},

    get perm() { return state().perm },
    get meta() { return callbacks.meta?.() ?? null },
    get name() { return proxy.is_new ? null : ((proxy.doc.name as string | undefined) ?? null) },
    get is_dirty() { return state().isDirty },
    get is_saving() { return state().isSaving },
    get is_loading() { return state().isLoading },
    get has_editable_fields() { return state().hasEditableFields },
    get has_tours() { return !!state().hasTours },
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
    start_tour(name?: string) { callbacks.ui?.startTour?.(name) },
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
    component?: (opts: ComponentDialogOptions) => Promise<unknown>
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
        throw new Error(typeof message === 'string' ? message : 'Server error', { cause: err })
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

    async open_dialog(name, opts = {}) {
      const component = appDialog(name)
      if (!component) throw new Error(`Unknown dialog "${name}"`)
      return callbacks.component?.({ ...opts, component })
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
 * The body of a client script's `new Function`: the script, then *call*.
 * In development a `//# sourceURL` names it, so it shows up in DevTools →
 * Sources as `clientscript/<DocType>/<script>.js` and takes breakpoints like
 * a normal file (otherwise it is an anonymous VM script).
 */
function scriptBody(doctype: string, entry: ClientScriptEntry, call: string): string {
  const body = `${entry.script};\n${call}`
  if (!import.meta.env.DEV) return body
  const name = entry.name.replace(/[^\w.-]+/g, '/').replace(/^\/+/, '')
  return `${body}\n//# sourceURL=clientscript/${doctype}/${name}${name.endsWith('.js') ? '' : '.js'}`
}

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
      // eslint-disable-next-line no-new-func -- client scripts are code by design
      const fn = new Function(
        'cur_frm',
        'frm',
        'grunt',
        '__',
        scriptBody(
          doctype,
          entry,
          `if (typeof ${event} === 'function') {\n` +
          `  return ${event}(cur_frm${event === 'on_change' ? `, '${changedField ?? ''}'` : ''});\n` +
          `}`,
        ),
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
      // eslint-disable-next-line no-new-func -- client scripts are code by design
      const fn = new Function(
        'listview',
        'grunt',
        '__',
        scriptBody(doctype, entry, `if (typeof setup_list === 'function') { return setup_list(listview); }`),
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
      // eslint-disable-next-line no-new-func -- client scripts are code by design
      const fn = new Function(
        'listview',
        'grunt',
        'change',
        '__',
        scriptBody(
          doctype,
          entry,
          `if (typeof on_quick_filter_change === 'function') { return on_quick_filter_change(listview, change); }`,
        ),
      )
      await fn(listview, gruntProxy, change, translate)
    } catch (err) {
      console.warn(`[ClientScript] Error in "${entry.name}" (on_quick_filter_change):`, err)
    }
  }
}
