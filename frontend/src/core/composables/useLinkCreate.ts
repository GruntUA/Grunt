/**
 * useLinkCreate — manages the "create new from Link field" round-trip.
 *
 * Flow:
 *   1. User clicks "Create" in a Link field on form A.
 *   2. `startLinkCreate()` saves form A's data as a draft in localStorage,
 *      stores the return context, and navigates to form B (the new linked doc).
 *   3. After form B is saved, `finishLinkCreate()` detects the return context,
 *      clears it, and navigates back to form A with the saved doc name.
 *   4. Form A mounts, `restoreLinkDraft()` detects the return payload in
 *      history.state, restores the draft, and sets the link field value.
 */

import { useRouter } from 'vue-router'

const DRAFT_PREFIX = 'grunt:link_draft:'
const RETURN_KEY = 'grunt:link_return'

export interface LinkReturnContext {
  returnPath: string
  fieldname: string
  linkedDoctype: string
}

// ── Write helpers ─────────────────────────────────────────────────────────────

function draftKey(doctype: string, id: string | null): string {
  return `${DRAFT_PREFIX}${doctype}:${id ?? 'new'}`
}

export function saveDraft(doctype: string, id: string | null, data: Record<string, unknown>): void {
  try {
    localStorage.setItem(draftKey(doctype, id), JSON.stringify(data))
  } catch { /* quota exceeded — ignore */ }
}

export function loadDraft(doctype: string, id: string | null): Record<string, unknown> | null {
  try {
    const raw = localStorage.getItem(draftKey(doctype, id))
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function clearDraft(doctype: string, id: string | null): void {
  localStorage.removeItem(draftKey(doctype, id))
}

// ── Return context ────────────────────────────────────────────────────────────

export function saveReturnContext(ctx: LinkReturnContext): void {
  localStorage.setItem(RETURN_KEY, JSON.stringify(ctx))
}

export function loadReturnContext(): LinkReturnContext | null {
  try {
    const raw = localStorage.getItem(RETURN_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function clearReturnContext(): void {
  localStorage.removeItem(RETURN_KEY)
}

// ── Main composable ───────────────────────────────────────────────────────────

export function useLinkCreate() {
  const router = useRouter()

  /**
   * Called when the user clicks "Create" in a Link field.
   *
   * @param linkedDoctype  The doctype to create (e.g. "Customer")
   * @param preset         Initial field values for the new doc, keyed by fieldname
   *                       (never `name` — that stays under the doctype's own autoname)
   * @param fieldname      Which field on the current form to fill after return
   * @param currentDoctype The doctype of the current form
   * @param currentId      The document id (null for new documents)
   * @param formData       Current (unsaved) form values to save as draft
   * @param workspace      Current workspace name (for route building)
   */
  function startLinkCreate(
    linkedDoctype: string,
    preset: Record<string, unknown>,
    fieldname: string,
    currentDoctype: string,
    currentId: string | null,
    formData: Record<string, unknown>,
    workspace?: string,
  ): void {
    const returnPath = workspace
      ? `/${workspace}/${currentDoctype}/${currentId ?? 'new'}`
      : `/${currentDoctype}/${currentId ?? 'new'}`

    saveDraft(currentDoctype, currentId, formData)
    saveReturnContext({ returnPath, fieldname, linkedDoctype })

    const newPath = workspace
      ? `/${workspace}/${linkedDoctype}/new`
      : `/${linkedDoctype}/new`

    const initialData = Object.keys(preset).length > 0 ? preset : null

    router.push({
      path: newPath,
      state: initialData ? { initial_data: JSON.stringify(initialData) } : undefined,
    })
  }

  /**
   * Called after a new document is successfully saved.
   * If a return context exists for this doctype, navigate back.
   *
   * @param savedDoctype  The doctype that was just saved
   * @param savedName     The `name` field of the saved document
   * @returns `true` if a return navigation was triggered
   */
  function finishLinkCreate(savedDoctype: string, savedName: string): boolean {
    const ctx = loadReturnContext()
    if (!ctx || ctx.linkedDoctype !== savedDoctype) return false

    clearReturnContext()

    router.replace({
      path: ctx.returnPath,
      // Pass back: which field to set + what value, keyed by "link_return"
      state: {
        link_return: JSON.stringify({
          fieldname: ctx.fieldname,
          value: savedName,
          // Encode draft key so the return form knows where to find draft
          draftDoctype: ctx.returnPath.split('/').at(-2) ?? '',
          draftId: ctx.returnPath.split('/').at(-1) ?? 'new',
        }),
      },
    })
    return true
  }

  /**
   * Called on mount of any form.
   * Detects if we returned from a link-create flow, restores the draft,
   * and returns the `{fieldname, value}` to set — or null if not applicable.
   */
  function restoreLinkDraft(
    _doctype: string,
    _id: string | null,
    form: Record<string, unknown>,
  ): { fieldname: string; value: string } | null {
    const state = window.history.state as Record<string, unknown> | null
    if (!state?.link_return) return null

    try {
      const payload = JSON.parse(state.link_return as string) as {
        fieldname: string
        value: string
        draftDoctype: string
        draftId: string
      }

      // Restore draft data into the form
      const draft = loadDraft(payload.draftDoctype, payload.draftId === 'new' ? null : payload.draftId)
      if (draft) {
        Object.assign(form, draft)
        clearDraft(payload.draftDoctype, payload.draftId === 'new' ? null : payload.draftId)
      }

      // Clear the history state so refresh doesn't re-apply
      window.history.replaceState(
        { ...state, link_return: undefined },
        '',
      )

      return { fieldname: payload.fieldname, value: payload.value }
    } catch {
      return null
    }
  }

  return { startLinkCreate, finishLinkCreate, restoreLinkDraft }
}
