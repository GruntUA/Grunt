import { nextTick, type Ref } from 'vue'
import type { Router } from 'vue-router'

import { clearScriptCache } from '@/core/scripting/executor'
import { useAppStore } from '@/stores/app'
import type { DocType } from '@/types'
import type { QueryClient } from '@tanstack/vue-query'

interface UseFormSaveParams {
  doctype: string
  id: string | null
  workspace?: string
  dt: Ref<DocType | null>
  form: Ref<Record<string, unknown>>
  validationErrors: Ref<Record<string, string>>
  save: () => Promise<unknown>
  runScriptEvent: (event: 'validate' | 'before_save' | 'after_save', changedField?: string) => Promise<boolean>
  validateForm: () => boolean
  focusFirstError: () => void
  markAllowLeave: () => void
  finishLinkCreate: (doctype: string, docname: string) => boolean
  queryClient: QueryClient
  dtStore: { invalidate: (doctype: string) => void }
  router: Router
  toast: {
    success: (message: string) => void
    error: (message: string) => void
  }
}

const CYRILLIC_TO_LATIN: Record<string, string> = {
  а: 'a', б: 'b', в: 'v', г: 'h', ґ: 'g', д: 'd', е: 'e', є: 'ye', ж: 'zh', з: 'z', и: 'y',
  і: 'i', ї: 'yi', й: 'y', к: 'k', л: 'l', м: 'm', н: 'n', о: 'o', п: 'p', р: 'r', с: 's',
  т: 't', у: 'u', ф: 'f', х: 'kh', ц: 'ts', ч: 'ch', ш: 'sh', щ: 'shch', ь: '', ю: 'yu',
  я: 'ya', ы: 'y', э: 'e', ъ: '', ё: 'yo',
}

function makeDocTypeNameFromLabel(label: string): string {
  const transliterated = Array.from(label)
    .map((ch) => {
      const lower = ch.toLowerCase()
      const mapped = CYRILLIC_TO_LATIN[lower]
      if (!mapped) return ch
      return ch === lower ? mapped : `${mapped.charAt(0).toUpperCase()}${mapped.slice(1)}`
    })
    .join('')

  const parts = transliterated
    .replace(/[^a-zA-Z0-9]+/g, ' ')
    .trim()
    .split(/\s+/)
    .filter(Boolean)

  let pascal = parts
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join('')
    .replace(/[^a-zA-Z0-9]/g, '')

  if (!pascal) return ''
  if (!/^[A-Za-z]/.test(pascal)) pascal = `DocType${pascal}`
  return pascal
}

export function useFormSave(params: UseFormSaveParams) {
  async function handleSave() {
    // Ensure pending watcher/emit chains (e.g. builder tab -> form model) are applied.
    await nextTick()

    if (params.doctype === 'DocType' && !params.id) {
      const currentName = String(params.form.value.name ?? '').trim()
      if (!currentName) {
        const label = String(params.form.value.label ?? '').trim()
        const generated = makeDocTypeNameFromLabel(label)
        if (generated) {
          params.form.value.name = generated
        }
      }
    }

    params.validationErrors.value = {}

    if (!params.validateForm()) {
      return
    }

    const valid = await params.runScriptEvent('validate')
    if (valid === false) return

    await params.runScriptEvent('before_save')

    try {
      const saved = await params.save()
      params.toast.success('Збережено')
      void params.runScriptEvent('after_save')
      params.dtStore.invalidate(params.doctype)
      params.queryClient.invalidateQueries({ queryKey: ['documents', params.doctype] })

      if (params.doctype === 'ClientScript') {
        clearScriptCache()
      }

      if (params.doctype === 'AppMenu') {
        const name = params.id ?? (saved as { name: string }).name
        useAppStore().markStale(name)
      }

      if (!params.id) {
        params.markAllowLeave()
        const savedDoc = saved as { id: string; name: string }

        if (params.finishLinkCreate(params.doctype, savedDoc.name)) {
          return
        }

        const path = params.workspace
          ? `/${params.workspace}/${params.doctype}/${savedDoc.id}`
          : `/${params.doctype}/${savedDoc.id}`
        params.router.replace(path)
      }
    } catch (error: unknown) {
      const err = error as {
        response?: {
          status?: number
          data?: {
            detail?: string | string[]
            error?: {
              message?: string
              details?: string[]
            }
          }
        }
      }
      const status = err?.response?.status
      const apiMessage = err?.response?.data?.error?.message
      const detailMsg = err?.response?.data?.detail

      // Any 4xx with a structured error message → show it directly
      if (status && status >= 400 && status < 500 && status !== 422 && (apiMessage || detailMsg)) {
        const msg = typeof apiMessage === 'string' && apiMessage.trim()
          ? apiMessage
          : typeof detailMsg === 'string' && detailMsg.trim()
            ? detailMsg
            : 'Помилка'
        params.toast.error(msg)
        return
      }

      if (err?.response?.status === 422) {
        const payload = err.response.data
        const legacyDetail = payload?.detail
        const apiDetails = payload?.error?.details

        const details: string[] = []
        const appendString = (value: unknown) => {
          if (typeof value === 'string' && value.trim().length > 0) details.push(value)
        }
        const appendFastApiValidation = (value: unknown) => {
          if (!value || typeof value !== 'object') return
          const entry = value as { loc?: unknown[]; msg?: unknown }
          const msg = typeof entry.msg === 'string' ? entry.msg.trim() : ''
          if (!msg) return
          const locParts = Array.isArray(entry.loc)
            ? entry.loc.filter((p): p is string | number => typeof p === 'string' || typeof p === 'number')
            : []
          const field = locParts.length > 0 ? String(locParts[locParts.length - 1]) : ''
          details.push(field ? `${field}: ${msg}` : msg)
        }

        if (Array.isArray(apiDetails)) {
          for (const item of apiDetails) appendString(item)
        }

        if (Array.isArray(legacyDetail)) {
          for (const item of legacyDetail) {
            appendString(item)
            appendFastApiValidation(item)
          }
        } else {
          appendString(legacyDetail)
          appendFastApiValidation(legacyDetail)
        }

        if (details.length === 0 && typeof apiMessage === 'string' && apiMessage.trim()) {
          details.push(apiMessage)
        }

        let hasFieldErrors = false
        for (const item of details) {
          const match = item.match(/^([a-zA-Z0-9_]+):\s*(.+)$/)
          if (!match) continue

          params.validationErrors.value[match[1]] = match[2]
          hasFieldErrors = true
        }

        // Business-rule fallback: duplicate department title in the same parent.
        const combinedMessage = details.join('; ')
        if (!hasFieldErrors && combinedMessage.includes('Підрозділ з такою назвою вже існує')) {
          params.validationErrors.value.title = combinedMessage
          hasFieldErrors = true
        }

        if (hasFieldErrors) {
          params.toast.error(combinedMessage || 'Перевірте правильність заповнення')
          params.focusFirstError()
        } else if (combinedMessage) {
          params.toast.error(combinedMessage)
        } else {
          const fallback = typeof apiMessage === 'string' && apiMessage.trim()
            ? apiMessage
            : 'Помилка валідації'
          params.toast.error(fallback)
        }
        return
      }

      params.toast.error('Помилка збереження')
    }
  }

  return {
    handleSave,
  }
}
