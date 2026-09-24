export {}

declare global {
  interface GruntMsgprintOptions {
    title?: string
    message: string
    indicator?: string
  }

  interface GruntFormField {
    fieldname: string
    label?: string
    fieldtype: string
    default?: unknown
  }

  interface GruntFormOptions {
    title: string
    primaryLabel?: string
    fields: GruntFormField[]
  }

  /** A button / menu item — see frontend/src/core/actions.ts. */
  interface GruntActionDef<C> {
    id: string
    label: string | ((ctx: C) => string)
    placement?: 'primary' | 'toolbar' | 'menu' | 'bulk' | 'workflow'
    icon?: string
    icon_only?: boolean
    group?: string
    order?: number
    variant?: string
    shortcut?: string
    visible?: (ctx: C) => boolean
    enabled?: (ctx: C) => boolean
    busy?: (ctx: C) => boolean
    confirm?: string | ((ctx: C) => string)
    action: (ctx: C) => unknown
  }

  interface GruntActions<C> {
    add(def: GruntActionDef<C>): void
    update(id: string, patch: Partial<Omit<GruntActionDef<C>, 'id'>>): void
    remove(id: string): void
    get(id: string): GruntActionDef<C> | undefined
    list(): GruntActionDef<C>[]
    run(id: string): Promise<void>
  }

  interface GruntDocPerms {
    write: boolean
    delete: boolean
    create: boolean
  }

  interface FormProxy {
    doctype: string
    doc: Record<string, any>
    is_new: boolean
    readonly name: string | null
    readonly perm: GruntDocPerms
    readonly is_dirty: boolean
    readonly is_saving: boolean
    readonly is_loading: boolean
    readonly has_editable_fields: boolean
    /** Standard ids (global_form.js): save, refresh, print…, duplicate, discard, activity, links, share, rename, delete. */
    actions: GruntActions<FormProxy>
    get_selected(): Record<string, string[]>
    get_value(fieldname: string): any
    set_value(fieldname: string, value: unknown): void
    set_query(fieldname: string, fn: (doc: Record<string, any>) => Record<string, any>): void
    save(): Promise<void>
    reload(options?: { meta?: boolean }): Promise<void>
    delete(): void
    duplicate(): void
    discard(): void
    rename(): void
    share(): void
    show_links(): void
    toggle_activity(): void
    print(format?: string, options?: { autoprint?: boolean }): void
    /** Workflow transitions allowed now (reloaded before each `on_transitions`). */
    readonly transitions: { action: string; to_state: string; prompt_fields: string[] }[]
    apply_transition(action: string): Promise<void>
  }

  interface ListViewProxy {
    doctype: string
    /** Standard ids (global_list.js): add, refresh, export:<id>, edit_doctype, customize_quick_filters, create_report, bulk_edit, bulk_delete, fast_delete. */
    actions: GruntActions<ListViewProxy>
    readonly perm: GruntDocPerms
    readonly selected: string[]
    readonly all_selected: boolean
    readonly is_fetching: boolean
    readonly can_export: boolean
    readonly exporters: { id: string; label: string }[]
    refresh(options?: { meta?: boolean }): void
    new_doc(): void
    bulk_edit(): void
    bulk_delete(): void
    fast_delete(): void
    export(exporterId: string): void
    customize_quick_filters(): void
    create_report(): void
  }

  interface GruntClientGlobal {
    session: { user: string; full_name: string; roles: string[] }
    call(method: string, args?: Record<string, any>): Promise<any>
    call(payload: { method: string; args?: Record<string, any> }): Promise<any>
    msgprint(message: string | GruntMsgprintOptions): void | Promise<void>
    form(options: GruntFormOptions): Promise<any>
    route_options?: Record<string, unknown> | null
    set_route(...route: unknown[]): void
    open_route(...route: unknown[]): void
  }

  const grunt: GruntClientGlobal
  const __: (text: string) => string
}
