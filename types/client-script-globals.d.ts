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

  interface FormProxy {
    doc: Record<string, any>
    is_new: boolean
    get_selected(): Record<string, string[]>
    set_value(fieldname: string, value: unknown): void
    set_query(fieldname: string, fn: (doc: Record<string, any>) => Record<string, any>): void
    add_custom_button(
      label: string,
      action: () => void | Promise<void>,
      group?: string,
      options?: { variant?: string; color?: string; icon?: string; group?: string }
    ): void
    remove_custom_button(label: string, group?: string | null): void
    clear_custom_buttons(): void
    change_custom_button_type(label: string, group: string | null, buttonType: string): void
    add_button(
      label: string,
      action: () => void | Promise<void>,
      options?: { variant?: string; color?: string; icon?: string; group?: string }
    ): void
  }

  interface GruntClientGlobal {
    call(method: string, args?: Record<string, any>): Promise<any>
    call(payload: { method: string; args?: Record<string, any> }): Promise<any>
    msgprint(message: string | GruntMsgprintOptions): void | Promise<void>
    form(options: GruntFormOptions): Promise<any>
    route_options?: Record<string, unknown> | null
    set_route(...route: unknown[]): void
    open_route(...route: unknown[]): void
  }

  const grunt: GruntClientGlobal
  const frappe: GruntClientGlobal
  const __: (text: string) => string
}
