import { computed, ref, type Ref } from 'vue'

import type { DocType } from '@/types'

interface StartLinkCreateParams {
  linkedDoctype: string
  preset: Record<string, unknown>
  fieldname: string
  parentDoctype: string
  parentId: string | null
  formSnapshot: Record<string, unknown>
  workspace?: string
}

interface UseFormLinkCreationParams {
  doctype: string
  id: string | null
  workspace?: string
  form: Ref<Record<string, unknown>>
  markAllowLeave: () => void
  loadDocType: (doctype: string) => Promise<DocType>
  startLinkCreate: (params: StartLinkCreateParams) => void
  navigateToNew: (linkedDoctype: string, preset: Record<string, unknown>) => void
}

export function useFormLinkCreation(params: UseFormLinkCreationParams) {
  const quickEntryDt = ref<DocType | null>(null)
  const quickEntryPreset = ref<Record<string, unknown>>({})
  const quickEntryFieldname = ref('')

  const isQuickEntryOpen = computed(() => Boolean(quickEntryDt.value))

  async function handleCreateNew(linkedDoctype: string, preset: string | Record<string, unknown>, fieldname: string) {
    const linkedDt = await params.loadDocType(linkedDoctype)

    // A typed search string becomes the new document's title-field value (a
    // sensible display default) — never its `name` (primary key). The `name`
    // column is owned by the target DocType's own autoname scheme; stuffing
    // free text into it here would silently hijack the naming series (see
    // _build_initial_row, which always honors an explicit `data["name"]`).
    const resolvedPreset: Record<string, unknown> =
      typeof preset === 'string'
        ? (preset && linkedDt?.title_field && linkedDt.title_field !== 'name'
            ? { [linkedDt.title_field]: preset }
            : {})
        : (preset || {})

    if (linkedDt?.quick_entry) {
      quickEntryDt.value = linkedDt
      quickEntryPreset.value = resolvedPreset
      quickEntryFieldname.value = fieldname
      return
    }

    params.markAllowLeave()

    // Dashboard "+" has no fieldname — use simple navigation with query params
    // so there's no unwanted return-flow after saving the new document.
    if (!fieldname && typeof preset !== 'string') {
      params.navigateToNew(linkedDoctype, preset)
      return
    }

    params.startLinkCreate({
      linkedDoctype,
      preset: resolvedPreset,
      fieldname,
      parentDoctype: params.doctype,
      parentId: params.id,
      formSnapshot: { ...params.form.value },
      workspace: params.workspace,
    })
  }

  function onQuickEntrySaved(docname: string) {
    if (quickEntryFieldname.value) {
      params.form.value[quickEntryFieldname.value] = docname
    }
    quickEntryDt.value = null
  }

  function closeQuickEntry() {
    quickEntryDt.value = null
  }

  return {
    quickEntryDt,
    quickEntryPreset,
    isQuickEntryOpen,
    handleCreateNew,
    onQuickEntrySaved,
    closeQuickEntry,
  }
}
