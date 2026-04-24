import { ref, computed, watch } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { docsApi } from '@/core/api/docs'
import type { GruntDocument } from '@/types'

export function useDocument(doctype: string, id: string | null) {
  const queryClient = useQueryClient()

  const { data: document, isLoading } = useQuery({
    queryKey: ['document', doctype, id],
    queryFn: () => docsApi.get(doctype, id!),
    enabled: computed(() => !!id),
  })

  const form = ref<Record<string, unknown>>({})

  watch(document, (doc) => {
    if (doc) form.value = { ...doc }
  }, { immediate: true })

  const isDirty = computed(() =>
    JSON.stringify(form.value) !== JSON.stringify(document.value)
  )

  const { mutateAsync: save, isPending: isSaving } = useMutation({
    mutationFn: () => id
      ? docsApi.update(doctype, id, form.value)
      : docsApi.create(doctype, form.value),
    onSuccess: (saved: GruntDocument) => {
      queryClient.setQueryData(['document', doctype, saved.id], saved)
      form.value = { ...saved }
      queryClient.invalidateQueries({ queryKey: ['documents', doctype] })
    }
  })

  const { mutateAsync: remove } = useMutation({
    mutationFn: () => docsApi.delete(doctype, id!),
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

  return { document, form, isLoading, isDirty, isSaving, save, remove, rename }
}
