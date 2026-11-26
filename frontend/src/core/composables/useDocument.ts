import { ref, computed, watch } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { docsApi } from '@/core/api/docs'
import { clearFormDraft } from '@/core/composables/useFormDraft'
import type { GruntDocument } from '@/types'

export function useDocument(doctype: string, id: string | null) {
  const queryClient = useQueryClient()

  const { data: document, isLoading, isError, refetch } = useQuery({
    queryKey: ['document', doctype, id],
    queryFn: () => docsApi.get(doctype, id!),
    enabled: computed(() => !!id),
  })

  const form = ref<Record<string, unknown>>({})
  const savedBaseline = ref<string>(JSON.stringify({}))

  const isDirty = computed(() =>
    JSON.stringify(form.value) !== savedBaseline.value
  )

  // A refetched copy (another user's save) never overwrites unsaved edits -
  // also the ones made while the request was in flight. Saving them over the
  // outdated copy is refused, and `reload()` brings the stored document.
  watch(document, (doc) => {
    if (doc && !isDirty.value) {
      form.value = { ...doc }
      savedBaseline.value = JSON.stringify(doc)
    }
  }, { immediate: true })

  const markClean = () => {
    savedBaseline.value = JSON.stringify(form.value)
  }

  const { mutateAsync: save, isPending: isSaving } = useMutation({
    mutationFn: () => id
      ? docsApi.update(doctype, id, form.value)
      : docsApi.create(doctype, form.value),
    onSuccess: (saved: GruntDocument) => {
      queryClient.setQueryData(['document', doctype, saved.id], saved)
      form.value = { ...saved }
      savedBaseline.value = JSON.stringify(saved)
      clearFormDraft(doctype, id)
      queryClient.invalidateQueries({ queryKey: ['documents', doctype] })
    }
  })

  /** Drop the edits (and their draft) and load the stored document again -
   *  after a save was refused as based on an outdated copy. The form is set
   *  here, not by the watcher: an unchanged refetch would not trigger it. */
  const reload = async () => {
    const { data: fresh } = await refetch()
    if (!fresh) return
    form.value = { ...fresh }
    savedBaseline.value = JSON.stringify(fresh)
    clearFormDraft(doctype, id)
  }

  const { mutateAsync: remove } = useMutation({
    mutationFn: (replaceWith?: string) => docsApi.delete(doctype, id!, replaceWith),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents', doctype] })
    }
  })

  const { mutateAsync: rename } = useMutation({
    mutationFn: (newId: string) => docsApi.rename(doctype, id!, newId),
    onSuccess: (saved: GruntDocument) => {
      queryClient.setQueryData(['document', doctype, saved.id], saved)
      queryClient.invalidateQueries({ queryKey: ['documents', doctype] })
    }
  })

  return { document, form, isLoading, isError, isDirty, isSaving, save, reload, remove, rename, markClean }
}
