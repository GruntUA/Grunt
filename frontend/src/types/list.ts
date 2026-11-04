/** List-view state: quick filters, active filters, view menu items. */

export interface QuickFilterOnChange {
  mode: 'local' | 'external'
  source?: string
  debounce_ms?: number
}

export interface QuickFilter {
  id: string
  field: string
  operator: string
  label?: string
  input_type: string  // 'text' | 'date' | 'year' | 'select' | 'check' | 'number' | 'link'
  default_value?: string | null
  /** Explicit list of select options; overrides field.options when set */
  options?: string[] | null
  on_change: QuickFilterOnChange
  enabled_in: Array<'list' | 'tree'>
}

/** A single active filter - used by FilterBar, DocTypeList, and docsApi */
export interface ActiveFilter {
  fieldname: string
  label: string
  fieldtype?: string   // stored for display logic in chips
  op: string          // display op: '=', '!=', 'like', '>', '<', '>=', '<='
  value: string
  displayValue?: string  // human-readable label (Link fields: title instead of name)
}

/** A menu item a list view (e.g. the map) contributes to the list's «⋯» menu. */
export interface ScriptMenuItem {
  label: string
  action: () => void | Promise<void>
  icon?: string           // reserved for future icon support
  separator_before?: boolean
}
