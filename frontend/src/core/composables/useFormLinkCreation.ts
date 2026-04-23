import { computed, ref, type Ref } from 'vue'

import type { DocType } from '@/types'

interface StartLinkCreateParams {
  linkedDoctype: string
  preset: string
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
}

export function useFormLinkCreation(params: UseFormLinkCreationParams) {
  const quickEntryDt = ref<DocType | null>(null)
  const quickEntryPreset = ref<Record<string, unknown>>({})
  const quickEntryFieldname = ref('')

  const isQuickEntryOpen = computed(() => Boolean(quickEntryDt.value))

  async function handleCreateNew(linkedDoctype: string, preset: string, fieldname: string) {
    const linkedDt = await params.loadDocType(linkedDoctype)
    if (linkedDt?.quick_entry) {
      quickEntryDt.value = linkedDt
      quickEntryPreset.value = preset ? { name: preset } : {}
      quickEntryFieldname.value = fieldname
      return
    }

    params.markAllowLeave()
    params.startLinkCreate({
      linkedDoctype,
      preset,
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
