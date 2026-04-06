/**
 * Global `grunt` helper — available as:
 *   - ES import:  import { grunt } from '@/core/grunt'
 *   - Script ctx: grunt.show_alert(...)  (injected via window.grunt in main.ts)
 *
 * Matches the GruntProxy interface from executor.ts so client scripts and
 * application code share the same API surface.
 */

import { toast } from 'vue-sonner'
import client from '@/core/api/client'
import { useDialog } from '@/core/composables/useDialog'
import type { MsgprintOptions, PromptOptions, DialogOptions } from '@/core/composables/useDialog'

export type AlertType = 'success' | 'error' | 'info' | 'warning'

export const grunt = {
  /**
   * Show a Sonner toast notification.
   *
   * @example
   * grunt.show_alert('Збережено', 'success')
   * grunt.show_alert({ message: 'Помилка', title: 'Деталі' }, 'error')
   */
  show_alert(
    msgOrOpts: string | { message: string; title?: string },
    type: AlertType = 'info',
  ): void {
    const text = typeof msgOrOpts === 'string' ? msgOrOpts : msgOrOpts.message
    const title = typeof msgOrOpts === 'object' ? msgOrOpts.title : undefined
    const msg = title ?? text
    const desc = title ? text : undefined
    if (type === 'success') toast.success(msg, { description: desc })
    else if (type === 'error') toast.error(msg, { description: desc })
    else if (type === 'warning') toast.warning(msg, { description: desc })
    else toast.info(msg, { description: desc })
  },

  msgprint(msgOrOpts: string | MsgprintOptions): Promise<void> {
    const dialog = useDialog()
    return dialog.msgprint(msgOrOpts)
  },

  prompt(labelOrOpts: string | PromptOptions, title?: string): Promise<string | null> {
    const dialog = useDialog()
    return dialog.prompt(labelOrOpts, title)
  },

  confirm(msg: string, title?: string): Promise<boolean> {
    const dialog = useDialog()
    return dialog.confirm(msg, title)
  },

  warn(title: string, message: string, primaryLabel?: string): Promise<boolean> {
    const dialog = useDialog()
    return dialog.warn(title, message, primaryLabel)
  },

  form(opts: DialogOptions): Promise<Record<string, unknown> | null> {
    const dialog = useDialog()
    return dialog.form(opts)
  },

  show_progress(title: string, count: number, total: number, description?: string): void {
    const dialog = useDialog()
    dialog.progress(title, count, total, description)
  },

  async call(opts: { method: string; args?: Record<string, unknown> }): Promise<unknown> {
    try {
      const { data } = await client.post(`/api/v1/method/${opts.method}`, opts.args ?? {})
      return data?.data
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      throw new Error(e?.response?.data?.detail || 'Server error')
    }
  },

  throw(msg: string): never {
    throw new Error(msg)
  },
}
