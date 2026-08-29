/**
 * useDocActions — turns a DocType's declarative `actions` bindings into
 * toolbar buttons, alongside client-script buttons.
 *
 * Each binding references an action registered in an app's Python code
 * (`@doc_action`). Clicking a button POSTs to `grunt.actions.run`, which
 * re-validates the binding server-side, runs the handler, then (by default)
 * reloads the form. A `condition` expression on the binding is evaluated
 * against the current form data to show/hide the button reactively.
 */
import { computed, unref } from 'vue'
import type { MaybeRefOrGetter, Ref } from 'vue'

import client from '@/core/api/client'
import { toast } from '@/core/composables/useToast'
import type { DocType, ScriptButton } from '@/types'

interface UseDocActionsOptions {
  doctype: string
  id: string | null
  dt: Ref<DocType | null>
  /** Current form/document data — used for `condition` evaluation and as the doc id source. */
  form: MaybeRefOrGetter<Record<string, unknown>>
  /** Reload the document after a successful action (unless the handler opts out). */
  reload: () => void | Promise<void>
}

function evalCondition(expr: string, doc: Record<string, unknown>): boolean {
  try {
    // eslint-disable-next-line no-new-func
    const fn = new Function('doc', `"use strict"; return (${expr});`)
    return Boolean(fn(doc))
  } catch (err) {
    console.warn('[doc-action] bad condition:', expr, err)
    return false
  }
}

export function useDocActions(options: UseDocActionsOptions) {
  const buttons = computed<ScriptButton[]>(() => {
    const bindings = options.dt.value?.actions ?? []
    if (!bindings.length || !options.id) return []

    const doc = (typeof options.form === 'function' ? options.form() : unref(options.form)) ?? {}

    return bindings
      .filter((b) => !b.hidden && !b._missing)
      .filter((b) => !b.condition || evalCondition(b.condition, doc as Record<string, unknown>))
      .map((b) => ({
        label: b._label || b.label || b.action,
        icon: b._icon || undefined,
        group: b._group || b.group || undefined,
        severity: b._variant || b.variant || 'outline',
        action: () => runAction(b.action, b._label || b.label || b.action, b._confirm ?? null),
      }))
  })

  async function runAction(action: string, label: string, confirmMsg: string | null) {
    if (confirmMsg && !window.confirm(confirmMsg)) return
    const doc = (typeof options.form === 'function' ? options.form() : unref(options.form)) ?? {}
    const docId = (doc as Record<string, unknown>).name ?? options.id
    try {
      const { data } = await client.post('/api/v1/method/grunt.actions.run', {
        doctype: options.doctype,
        action,
        doc_id: docId,
        args: {},
      })
      const payload = data?.data ?? {}
      if (payload.copy && typeof navigator !== 'undefined' && navigator.clipboard) {
        try {
          await navigator.clipboard.writeText(String(payload.copy))
        } catch {
          /* clipboard blocked — the message toast still shows the value */
        }
      }
      toast.success(payload.message || `${label}: готово`)
      if (payload.refresh !== false) await options.reload()
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { error?: { message?: string }; detail?: string } } })
          ?.response?.data
      toast.error(detail?.error?.message || detail?.detail || `${label}: помилка`)
    }
  }

  return { docActionButtons: buttons }
}
