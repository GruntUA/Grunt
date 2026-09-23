/**
 * useFormDraft — protects unsaved form edits from being lost to an accidental
 * page reload, tab close, or crash.
 *
 * While the form is dirty, the current `form.value` is debounce-written to
 * localStorage. On (re)mount, `checkForDraft()` looks up a leftover draft so
 * the caller can offer it back to the user (a banner, typically) via
 * `pendingDraft` / `restoreDraft()` / `discardDraft()`. The draft is cleared
 * automatically once the document is actually saved (see `clearFormDraft`,
 * called from `useDocument`'s save mutation) — never on mere navigation, since
 * that's exactly the case this exists to survive.
 */
import { onMounted, onUnmounted, ref, watch, type Ref } from 'vue'

const DRAFT_PREFIX = 'grunt:draft:'
const STALE_AFTER_MS = 7 * 24 * 60 * 60 * 1000 // 7 днів — старі чернетки не пропонуємо

export interface StoredFormDraft {
  data: Record<string, unknown>
  savedAt: string
}

function draftKey(doctype: string, id: string | null): string {
  return `${DRAFT_PREFIX}${doctype}:${id ?? 'new'}`
}

export function saveFormDraft(doctype: string, id: string | null, data: Record<string, unknown>): void {
  try {
    const payload: StoredFormDraft = { data, savedAt: new Date().toISOString() }
    localStorage.setItem(draftKey(doctype, id), JSON.stringify(payload))
  } catch { /* сховище переповнене — чернетку просто не збережено */ }
}

export function loadFormDraft(doctype: string, id: string | null): StoredFormDraft | null {
  try {
    const raw = localStorage.getItem(draftKey(doctype, id))
    if (!raw) return null
    const parsed = JSON.parse(raw) as StoredFormDraft
    if (Date.now() - new Date(parsed.savedAt).getTime() > STALE_AFTER_MS) {
      localStorage.removeItem(draftKey(doctype, id))
      return null
    }
    return parsed
  } catch {
    return null
  }
}

export function clearFormDraft(doctype: string, id: string | null): void {
  localStorage.removeItem(draftKey(doctype, id))
}

export interface UseFormDraftParams {
  doctype: string
  id: string | null
  form: Ref<Record<string, unknown>>
  isDirty: Ref<boolean>
}

export function useFormDraft(params: UseFormDraftParams) {
  const pendingDraft = ref<StoredFormDraft | null>(null)

  /** Looks up a leftover draft. Call once the real document data is in `form`. */
  function checkForDraft(): void {
    pendingDraft.value = loadFormDraft(params.doctype, params.id)
  }

  function restoreDraft(): void {
    if (!pendingDraft.value) return
    Object.assign(params.form.value, pendingDraft.value.data)
    pendingDraft.value = null
  }

  function discardDraft(): void {
    clearFormDraft(params.doctype, params.id)
    pendingDraft.value = null
  }

  // Debounced autosave — mirrors the deep-compare style `isDirty` already uses in useDocument.
  let timer: ReturnType<typeof setTimeout> | undefined
  watch(
    () => (params.isDirty.value ? JSON.stringify(params.form.value) : null),
    (snapshot) => {
      clearTimeout(timer)
      if (snapshot === null) return
      timer = setTimeout(() => saveFormDraft(params.doctype, params.id, params.form.value), 800)
    },
  )

  function beforeUnloadHandler(e: BeforeUnloadEvent) {
    if (!params.isDirty.value) return
    e.preventDefault()
    e.returnValue = ''
  }
  onMounted(() => window.addEventListener('beforeunload', beforeUnloadHandler))
  onUnmounted(() => {
    window.removeEventListener('beforeunload', beforeUnloadHandler)
    clearTimeout(timer)
  })

  return { pendingDraft, checkForDraft, restoreDraft, discardDraft }
}
