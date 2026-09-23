/**
 * Global `grunt` helper — available as:
 *   - ES import:  import { grunt } from '@/core/grunt'
 *   - Script ctx: grunt.show_alert(...)  (injected via window.grunt in main.ts)
 *
 * Matches the GruntProxy interface from executor.ts so client scripts and
 * application code share the same API surface.
 */

import { toast } from '@/core/composables/useToast'
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
    if (type === 'success') toast.success(text)
    else if (type === 'error') toast.error(text)
    else if (type === 'warning') toast.warning(text)
    else toast.info(text)
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

  /**
   * "Select from a list" dialog. Resolves with the picked row(s), or null if
   * cancelled.
   *
   * @example
   * const rows = await grunt.select({
   *   title: 'Оберіть заявки',
   *   columns: [{ key: 'name', label: 'Номер' }, { key: 'status', label: 'Статус', width: '120px' }],
   *   rows: await grunt.call({ method: 'app.api.pending_requests' }),
   *   primaryLabel: 'Отримати позиції',
   * })
   */
  select(opts: Parameters<ReturnType<typeof useDialog>['select']>[0]) {
    const dialog = useDialog()
    return dialog.select(opts)
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

  /**
   * WebAuthn / passkey helpers — drive the `/api/v1/auth/webauthn/*` ceremonies
   * from client scripts and app code without touching the browser API directly.
   *
   * @example
   * const { label } = await grunt.passkey.register('MacBook Touch ID')
   */
  passkey: {
    isSupported(): boolean {
      return typeof window !== 'undefined' && !!window.PublicKeyCredential
    },

    async register(
      label?: string,
      opts?: { mode?: 'cross-device' },
    ): Promise<{ name: string; label: string }> {
      const { authApi } = await import('@/core/api/auth')
      const { createPasskey, isWebAuthnSupported } = await import(
        '@/core/composables/useWebAuthn'
      )
      if (!isWebAuthnSupported()) {
        throw new Error('Цей браузер не підтримує ключі доступу')
      }
      const { options, challenge_token } = await authApi.enrollBegin(
        'webauthn',
        opts?.mode ? { mode: opts.mode } : {},
      )
      const credential = await createPasskey(options)
      return authApi.enrollComplete('webauthn', {
        challenge_token,
        response: credential,
        label,
      })
    },

    async list() {
      const { authApi } = await import('@/core/api/auth')
      return authApi.listPasskeys()
    },

    async rename(name: string, label: string): Promise<void> {
      const { authApi } = await import('@/core/api/auth')
      await authApi.renamePasskey(name, label)
    },

    async remove(name: string): Promise<void> {
      const { authApi } = await import('@/core/api/auth')
      await authApi.deletePasskey(name)
    },
  },

  /** Browser health checks (service worker, offline cache & queue, storage) — see core/browserHealth.ts. */
  health: {
    async diagnose_browser() {
      const { diagnoseBrowser } = await import('@/core/browserHealth')
      return diagnoseBrowser()
    },

    async persist_storage(): Promise<boolean> {
      const { persistStorage } = await import('@/core/browserHealth')
      return persistStorage()
    },
  },
}
