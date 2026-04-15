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

// ── Types ────────────────────────────────────────────────────────────────

export type DialogFieldType = 'Text' | 'LongText' | 'Int' | 'Float' | 'Date' | 'Datetime' | 'Select' | 'Check' | 'HTML'

export interface DialogField {
  fieldname: string
  label: string
  fieldtype?: DialogFieldType
  required?: boolean
  default?: unknown
  options?: string // for Select: newline-separated
  placeholder?: string
}

export interface MsgprintOptions {
  message: string
  title?: string
  indicator?: 'green' | 'red' | 'orange' | 'blue' | 'yellow' | string
}

export interface PromptOptions {
  label: string
  fieldname?: string
  fieldtype?: DialogFieldType
  required?: boolean
  default?: unknown
  options?: string
  placeholder?: string
  title?: string
}

export type DialogSize = 'small' | 'large' | 'extra-large'

export type DialogType = 'msgprint' | 'confirm' | 'prompt' | 'warn' | 'dialog' | 'progress'

export interface DialogOptions {
  title: string
  fields: DialogField[]
  primaryLabel?: string
  size?: DialogSize
}

export interface DialogState {
  open: boolean
  type: DialogType
  title: string
  message: string
  indicator: string | null
  fields: DialogField[]
  primaryLabel: string
  size: DialogSize
  proceedAction: (() => void | Promise<void>) | null
  progress: { count: number; total: number; percent: number; description: string | null }
  resolve: ((value: unknown) => void) | null
}

// ── Singleton state ──────────────────────────────────────────────────────

const state = reactive<DialogState>({
  open: false,
  type: 'msgprint',
  title: '',
  message: '',
  indicator: null,
  fields: [],
  primaryLabel: 'OK',
  size: 'small',
  proceedAction: null,
  progress: { count: 0, total: 0, percent: 0, description: null },
  resolve: null,
})

function reset() {
  state.open = false
  state.type = 'msgprint'
  state.title = ''
  state.message = ''
  state.indicator = null
  state.fields = []
  state.primaryLabel = 'OK'
  state.size = 'small'
  state.proceedAction = null
  state.progress = { count: 0, total: 0, percent: 0, description: null }
  state.resolve = null
}

// ── Public API ───────────────────────────────────────────────────────────

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
      state.title = title ?? 'Підтвердження'
      state.message = message
      state.resolve = resolve as (value: unknown) => void
      state.open = true
    })
  }

  /**
   * Prompt the user for a value.
   * Resolves with the entered value, or null if cancelled.
   */
  function prompt(labelOrOpts: string | PromptOptions, title?: string): Promise<string | null> {
    return new Promise((resolve) => {
      const opts: PromptOptions = typeof labelOrOpts === 'string'
        ? { label: labelOrOpts }
        : labelOrOpts
      reset()
      state.type = 'prompt'
      state.title = opts.title ?? title ?? ''
      state.fields = [{
        fieldname: opts.fieldname ?? 'value',
        label: opts.label,
        fieldtype: opts.fieldtype ?? 'Text',
        required: opts.required ?? false,
        default: opts.default,
        options: opts.options,
        placeholder: opts.placeholder,
      }]
      state.resolve = resolve as (value: unknown) => void
      state.open = true
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
    primaryLabel: string = 'Продовжити',
  ): Promise<boolean> {
    return new Promise((resolve) => {
      reset()
      state.type = 'warn'
      state.title = title
      state.message = message
      state.indicator = 'orange'
      state.primaryLabel = primaryLabel
      state.resolve = resolve as (value: unknown) => void
      state.open = true
    })
  }

  /**
   * Open a form dialog with one or more fields.
   * Resolves with the submitted values dict, or null if cancelled.
   *
   * Mirrors `frappe.ui.Dialog` / `frappe.prompt` with multiple fields.
   *
   * @example
   * const values = await dialog.form({
   *   title: 'Новий клієнт',
   *   fields: [
   *     { fieldname: 'name',  label: 'Назва',  fieldtype: 'Text',   required: true },
   *     { fieldname: 'email', label: 'Email',  fieldtype: 'Text' },
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
      state.resolve = resolve as (value: unknown) => void
      state.open = true
    })
  }

  /**
   * Show/update a progress bar. Does not block — call repeatedly to update.
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
    progress,
    close,
  }
}
