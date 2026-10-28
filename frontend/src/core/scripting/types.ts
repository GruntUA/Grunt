/**
 * Public types of the client-script API (`frm`, `listview`, `grunt`).
 * Re-exported from `executor.ts`, which implements them.
 */

import type { ActionsApi } from '@/core/actions'
import type { DialogSize } from '@/core/composables/useDialog'
import type { DocPerms } from '@/core/permissions'
import type { FormDashboardApi } from '@/core/scripting/formDashboard'
import type { DocType } from '@/types'

/** Callback registered via frm.set_query - returns filters for a link field. */
export type LinkQueryFn = (
  doc: Record<string, unknown>,
) => { filters: Record<string, string | string[]> } | Record<string, string | string[]>

/** Form proxy exposed to client scripts as `cur_frm`. */
export interface FormProxy {
  doctype: string
  doc: Record<string, unknown>
  fields: Record<string, unknown>[]
  /** The DocType definition (flags such as `is_signable`, views, …); null until loaded. */
  readonly meta: DocType | null
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
  /**
   * The area above the form - headline, indicators, progress, chart, heatmap,
   * custom sections, connection badge counts. Reset before every `on_load`.
   *
   * ```js
   * frm.dashboard.set_headline('Прострочено', 'red')
   * frm.dashboard.add_indicator('Оплачено: 12 000 ₴', 'green')
   * frm.dashboard.add_progress('Виконання', 65)
   * ```
   */
  dashboard: FormDashboardApi
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
  /** Delete every row the list matches (filters, search) without per-document hooks (System Manager). */
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
   * Open an app's dialog component (bench/apps/<app>/desk/dialogs/<Name>.vue).
   * Resolves with the value the component emits as `close`.
   *
   * ```js
   * const signed = await grunt.open_dialog('esign/SignDialog', {
   *   title: __('Sign'), props: { doctype: frm.doctype, name: frm.name },
   * })
   * ```
   */
  open_dialog: (name: string, opts?: { title?: string; props?: Record<string, unknown>; size?: DialogSize }) => Promise<unknown>
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
  /** The form has tours (FormTour) the user may take. */
  hasTours?: boolean
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
  startTour: (name?: string) => void
}

export interface ListViewState {
  perm: DocPerms
  selected: string[]
  isFetching: boolean
  exporters: ListExporterInfo[]
  canExport: boolean
  filters: Array<{ fieldname: string; op: string; value: string }>
}
