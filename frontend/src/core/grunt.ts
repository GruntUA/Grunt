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

  msgprint(msgOrOpts: string | { message: string; title?: string }): void {
    const text = typeof msgOrOpts === 'string' ? msgOrOpts : msgOrOpts.message
    const title = typeof msgOrOpts === 'object' ? msgOrOpts.title : undefined
    toast(title ?? text, { description: title ? text : undefined })
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

  async confirm(msg: string): Promise<boolean> {
    return window.confirm(msg)
  },
}
