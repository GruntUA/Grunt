/**
 * Imperative Dialog API for Grunt app developers.
 *
 * Provides promise-based dialogs callable from anywhere:
 *
 *   import { useDialog } from '@/core/composables/useDialog'
 *   const dialog = useDialog()
 *
 *   // Message dialog
 *   await dialog.msgprint('Документ збережено')
 *   await dialog.msgprint({ title: 'Увага', message: 'Перевірте дані', indicator: 'orange' })
 *
 *   // Confirmation
 *   const ok = await dialog.confirm('Видалити цей документ?')
 *
 *   // Prompt for a single value
 *   const name = await dialog.prompt('Введіть назву')
 *   const date = await dialog.prompt({ label: 'Дата', fieldtype: 'Date' })
 *
 *   // Show progress
 *   dialog.progress('Імпорт', 50, 200, 'Обробка рядків...')
 */

import { reactive } from 'vue'
import i18n from '@/plugins/i18n'
import type { FieldType } from '@/types'

const t = (key: string, params: Record<string, unknown> = {}): string => i18n.global.t(key, params)

// Types

export interface DialogTableColumn {
  /** Row property to read. */
  key: string
  label: string
  /** CSS width - e.g. '120px', '30%'. */
  width?: string
  align?: 'left' | 'right' | 'center'
  /** Custom cell -> HTML string (plain text is auto-escaped when omitted). */
  format?: (value: unknown, row: Record<string, unknown>) => string
}

/** Trailing per-row button in a Table field (delete / edit / …). */
export interface DialogTableRowAction {
  label: string
  variant?: 'default' | 'secondary' | 'outline' | 'ghost' | 'destructive'
  /** Tint the button in the destructive colour without a filled background. */
  danger?: boolean
  onClick: (row: Record<string, unknown>, ctx: {
    /** Styled yes/no over the dialog. */
    confirm: (message: string) => Promise<boolean>
    /** Replace the table's rows (e.g. after a delete + refetch). */
    setRows: (rows: Record<string, unknown>[]) => void
  }) => unknown | Promise<unknown>
}

export interface DialogField {
  fieldname: string
  label: string
  fieldtype?: FieldType
  required?: boolean
  default?: unknown
  options?: string // for Select: newline-separated; for Link: DocType name
  placeholder?: string
  read_only?: boolean
  description?: string
  /** HTML fields only: render inline (no dashed QR-style frame). */
  plain?: boolean
  /** Password fields only: show a live checklist of the password policy. */
  show_strength?: boolean

  // Table field
  /** Table: column spec. */
  columns?: DialogTableColumn[]
  /** Table: the rows to show. */
  rows?: Record<string, unknown>[]
  /** Table: unique row property (default 'name'). */
  rowKey?: string
  /** Table: allow selecting many rows (checkboxes). Default true. */
  multiple?: boolean
  /** Table: show selection checkboxes / row-click select. Default: `multiple !== false`. */
  selectable?: boolean
  /** Table: show the search box. Default true. */
  searchable?: boolean
  /** Table: scroll area max height. Default '320px'. */
  maxHeight?: string
  /** Table: text when there are no rows. */
  emptyText?: string
  /** Table: trailing per-row buttons. */
  rowActions?: DialogTableRowAction[]
}

/**
 * Extra action button on a `form` dialog. Unlike the primary button it does
 * NOT close the dialog - it runs an in-dialog operation (add row, delete row,
 * refresh…) and can rewrite fields via the controller. Call `ctx.close()` to
 * dismiss.
 */
export interface DialogActionButton {
  label: string
  variant?: 'default' | 'secondary' | 'outline' | 'ghost' | 'destructive'
  action: (ctx: {
    values: Record<string, unknown>
    /** Patch one field in place (e.g. `{ default: newHtml }`, `{ options: '…' }`). */
    setField: (fieldname: string, patch: Partial<DialogField>) => void
    /** Replace the whole field set and re-seed values. */
    setFields: (fields: DialogField[]) => void
    /** Styled yes/no shown *over* this dialog (no nested-dialog conflict). */
    confirm: (message: string) => Promise<boolean>
    /** Close the dialog, resolving `form()` with `value`. */
    close: (value?: unknown) => void
  }) => unknown | Promise<unknown>
}

export interface MsgprintOptions {
  message: string
  title?: string
  indicator?: 'green' | 'red' | 'orange' | 'blue' | 'yellow' | string
}

export interface PromptOptions {
  label: string
  fieldname?: string
  fieldtype?: FieldType
  required?: boolean
  default?: unknown
  options?: string
  placeholder?: string
  title?: string
}

export type DialogSize = 'small' | 'large' | 'extra-large'

/** `prompt`/`select` are `dialog` underneath, `warn` is a destructive `confirm`. */
export type DialogType = 'msgprint' | 'confirm' | 'dialog' | 'progress'

export interface DialogOptions {
  title: string
  fields: DialogField[]
  primaryLabel?: string
  size?: DialogSize
  /** Extra in-dialog action buttons (see {@link DialogActionButton}). */
  buttons?: DialogActionButton[]
}

export interface DialogState {
  open: boolean
  type: DialogType
  title: string
  message: string
  indicator: string | null
  fields: DialogField[]
  primaryLabel: string
  /** confirm only: paint the primary button destructive (`warn`). */
  destructive: boolean
  size: DialogSize
  buttons: DialogActionButton[]
  busyButton: number | null
  /** Transient yes/no overlay for an in-dialog action (see DialogActionButton.confirm). */
  actionConfirm: { message: string; resolve: (v: boolean) => void } | null
  progress: { count: number; total: number; percent: number; description: string | null }
  resolve: ((value: unknown) => void) | null
}

// Singleton state

const DEFAULT_STATE: Omit<DialogState, 'resolve'> = {
  open: false,
  type: 'msgprint',
  title: '',
  message: '',
  indicator: null,
  fields: [],
  primaryLabel: 'OK',
  destructive: false,
  size: 'small',
  buttons: [],
  busyButton: null,
  actionConfirm: null,
  progress: { count: 0, total: 0, percent: 0, description: null },
}

const state = reactive<DialogState>({ ...DEFAULT_STATE, resolve: null })

function reset() {
  Object.assign(state, DEFAULT_STATE, { resolve: null })
}

// Public API

export function useDialog() {
  /**
   * Show a message dialog. Resolves when the user closes it.
   */
  function msgprint(messageOrOpts: string | MsgprintOptions): Promise<void> {
    return new Promise((resolve) => {
      const opts = typeof messageOrOpts === 'string' ? { message: messageOrOpts } : messageOrOpts
      reset()
      state.type = 'msgprint'
      state.title = opts.title ?? ''
      state.message = opts.message
      state.indicator = opts.indicator ?? null
      state.resolve = resolve as (value: unknown) => void
      state.open = true
    })
  }

  /**
   * Show a confirmation dialog. Resolves with true (confirm) or false (cancel).
   */
  function confirm(message: string, title?: string): Promise<boolean> {
    return new Promise((resolve) => {
      reset()
      state.type = 'confirm'
      state.title = title ?? t('Confirmation')
      state.message = message
      state.primaryLabel = t('Confirm')
      state.resolve = resolve as (value: unknown) => void
      state.open = true
    })
  }

  /**
   * Prompt the user for a value.
   * Resolves with the entered value, or null if cancelled.
   */
  function prompt(labelOrOpts: string | PromptOptions, title?: string): Promise<string | null> {
    const opts: PromptOptions = typeof labelOrOpts === 'string' ? { label: labelOrOpts } : labelOrOpts
    const fieldname = opts.fieldname ?? 'value'
    return form({
      title: opts.title ?? title ?? '',
      fields: [{
        fieldname,
        label: opts.label,
        fieldtype: opts.fieldtype ?? 'Data',
        required: opts.required,
        default: opts.default,
        options: opts.options,
        placeholder: opts.placeholder,
      }],
    }).then((v) => {
      const value = v?.[fieldname]
      return value == null || value === '' ? null : String(value)
    })
  }

  /**
   * Show a warning dialog with a "Proceed" button.
   * Resolves with true if the user proceeds, false if cancelled.
   *
   * @example
   * const ok = await dialog.warn('Увага', 'Ця дія незворотна. Продовжити?')
   * const ok = await dialog.warn('Увага', 'Видалити всі записи?', 'Видалити')
   */
  function warn(
    title: string,
    message: string,
    primaryLabel: string = t('Continue'),
  ): Promise<boolean> {
    return new Promise((resolve) => {
      reset()
      state.type = 'confirm'
      state.title = title
      state.message = message
      state.primaryLabel = primaryLabel
      state.destructive = true
      state.resolve = resolve as (value: unknown) => void
      state.open = true
    })
  }

  /**
   * Open a form dialog with one or more fields.
   * Resolves with the submitted values dict, or null if cancelled.
   *
   * @example
   * const values = await dialog.form({
   *   title: 'Новий клієнт',
   *   fields: [
   *     { fieldname: 'name',  label: 'Назва',  fieldtype: 'Data',   required: true },
   *     { fieldname: 'email', label: 'Email',  fieldtype: 'Data' },
   *     { fieldname: 'type',  label: 'Тип',    fieldtype: 'Select', options: 'Фіз. особа\nЮр. особа' },
   *   ],
   *   primaryLabel: 'Створити',
   *   size: 'large',
   * })
   * if (values) console.log(values.name, values.email)
   */
  function form(opts: DialogOptions): Promise<Record<string, unknown> | null> {
    return new Promise((resolve) => {
      reset()
      state.type = 'dialog'
      state.title = opts.title
      state.fields = opts.fields
      state.primaryLabel = opts.primaryLabel ?? 'OK'
      state.size = opts.size ?? 'small'
      state.buttons = opts.buttons ?? []
      state.resolve = resolve as (value: unknown) => void
      state.open = true
    })
  }

  /**
   * Open a dialog that shows a selectable list/table. Resolves with the
   * selected row(s), or null if cancelled.
   *
   * @example
   * const picked = await dialog.select({
   *   title: 'Оберіть заявки',
   *   columns: [
   *     { key: 'name', label: 'Номер' },
   *     { key: 'schedule_date', label: 'Дата', width: '140px' },
   *     { key: 'status', label: 'Статус', width: '120px' },
   *   ],
   *   rows: await grunt.call({ method: '...' }),
   *   primaryLabel: 'Отримати позиції',
   * })
   * if (picked) console.log(picked)          // array of rows (multiple:true)
   */
  function select(opts: {
    title: string
    columns: DialogTableColumn[]
    rows: Record<string, unknown>[]
    rowKey?: string
    multiple?: boolean
    searchable?: boolean
    primaryLabel?: string
    size?: DialogSize
    description?: string
    maxHeight?: string
    /** Extra fields rendered above the table (e.g. quick filters). */
    fields?: DialogField[]
    buttons?: DialogActionButton[]
  }): Promise<Record<string, unknown>[] | Record<string, unknown> | null> {
    const multiple = opts.multiple ?? true
    const tableField: DialogField = {
      fieldname: '__selection',
      label: '',
      fieldtype: 'Table',
      columns: opts.columns,
      rows: opts.rows,
      rowKey: opts.rowKey ?? 'name',
      multiple,
      searchable: opts.searchable ?? true,
      maxHeight: opts.maxHeight,
      description: opts.description,
    }
    return form({
      title: opts.title,
      size: opts.size ?? 'extra-large',
      primaryLabel: opts.primaryLabel ?? t('Choose'),
      fields: [...(opts.fields ?? []), tableField],
      buttons: opts.buttons,
    }).then((v) => (v ? (v.__selection as any) ?? (multiple ? [] : null) : null))
  }

  /**
   * Show/update a progress bar. Does not block - call repeatedly to update.
   */
  function progress(title: string, count: number, total: number, description?: string) {
    state.type = 'progress'
    state.title = title
    state.progress = {
      count,
      total,
      percent: total > 0 ? Math.round((count / total) * 100) : 0,
      description: description ?? null,
    }
    state.open = true

    // Auto-close when complete
    if (count >= total) {
      setTimeout(() => {
        if (state.type === 'progress') reset()
      }, 800)
    }
  }

  /** Close the current dialog and resolve with a value. */
  function close(value?: unknown) {
    const r = state.resolve
    reset()
    if (r) r(value)
  }

  return {
    state,
    msgprint,
    confirm,
    prompt,
    warn,
    form,
    select,
    progress,
    close,
  }
}
