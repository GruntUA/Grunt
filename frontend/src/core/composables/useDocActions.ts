/**
 * useDocActions — registers a DocType's declarative `actions` bindings in the
 * form's action registry (core/actions.ts), next to script-registered actions.
 *
 * Each binding references an action registered in an app's Python code
 * (`@doc_action`). Clicking a button POSTs to `grunt.actions.run`, which
 * re-validates the binding server-side, runs the handler, then (by default)
 * reloads the form. A `condition` expression on the binding is evaluated
 * against the current form data to show/hide the button reactively.
 */
import { unref, watch } from 'vue'
import type { MaybeRefOrGetter, Ref } from 'vue'

import client from '@/core/api/client'
import type { DialogField } from '@/core/composables/useDialog'
import { useDialog } from '@/core/composables/useDialog'
import { toast } from '@/core/composables/useToast'
import type { DocActionField, DocType } from '@/types'
import type { ActionsApi } from '@/core/actions'
import type { FormProxy } from '@/core/scripting/executor'
import i18n from '@/plugins/i18n'

const t = (key: string): string => i18n.global.t(key)

interface UseDocActionsOptions {
  doctype: string
  id: string | null
  dt: Ref<DocType | null>
  /** Current form/document data — the doc id source when running an action. */
  form: MaybeRefOrGetter<Record<string, unknown>>
  /** The form's action registry to register the bindings in. */
  actions: ActionsApi<FormProxy>
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
  let registered: string[] = []

  // Re-register whenever the DocType definition changes (e.g. after a meta reload).
  watch(
    () => options.dt.value?.actions ?? [],
    (bindings) => {
      for (const id of registered) options.actions.remove(id)
      registered = []
      bindings
        .filter((b) => !b.hidden && !b._missing)
        .forEach((b, index) => {
          const id = `doc_action:${b.action}`
          const label = b._label || b.label || b.action
          registered.push(id)
          options.actions.add({
            id,
            label,
            icon: b._icon || undefined,
            group: b._group || b.group || undefined,
            variant: b._variant || b.variant || 'outline',
            placement: 'toolbar',
            order: 200 + index,
            visible: (frm) =>
              !frm.is_new && (!b.condition || evalCondition(b.condition, frm.doc as Record<string, unknown>)),
            action: () => runAction(b.action, label, b._confirm ?? null, b._fields ?? []),
          })
        })
    },
    { immediate: true },
  )

  async function runAction(
    action: string,
    label: string,
    confirmMsg: string | null,
    fields: DocActionField[],
  ) {
    let args: Record<string, unknown> = {}
    if (fields.length) {
      const values = await useDialog().form({
        title: label,
        fields: fields as DialogField[],
        primaryLabel: label,
      })
      if (values === null) return
      args = values
    } else if (confirmMsg && !window.confirm(confirmMsg)) {
      return
    }
    const doc = (typeof options.form === 'function' ? options.form() : unref(options.form)) ?? {}
    const docId = (doc as Record<string, unknown>).name ?? options.id
    try {
      const { data } = await client.post('/api/v1/method/grunt.actions.run', {
        doctype: options.doctype,
        action,
        doc_id: docId,
        args,
      })
      const payload = data?.data ?? {}
      if (payload.copy && typeof navigator !== 'undefined' && navigator.clipboard) {
        try {
          await navigator.clipboard.writeText(String(payload.copy))
        } catch {
          /* clipboard blocked — the message toast still shows the value */
        }
      }
      toast.success(payload.message || `${label}: ${t('done')}`)
      if (payload.refresh !== false) await options.reload()
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { error?: { message?: string }; detail?: string } } })
          ?.response?.data
      toast.error(detail?.error?.message || detail?.detail || `${label}: ${t('error')}`)
    }
  }

}
