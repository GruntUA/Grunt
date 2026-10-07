/**
 * Shared logic for the Attach and Image fields: reads the stored file URL,
 * resolves its display name via the files API, and exposes select / remove.
 */
import { ref, computed, watch, inject } from 'vue'
import type { AttachmentResult } from '@/components/fields/Attach/attachment'
import { filesApi } from '@/core/api/files'
import { extractFileId } from '@/core/fileUtils'

export interface DocContext {
  doctype: string
  getId: () => string | null
}

interface AttachProps {
  field: { read_only?: boolean }
  modelValue: unknown
  disabled?: boolean
}

export function useAttachmentField(
  props: AttachProps,
  emit: (e: 'update:modelValue', value: unknown) => void,
) {
  const docContext = inject<DocContext | null>('docContext', null)

  const isDisabled = computed(() => !!(props.disabled || props.field.read_only))

  const currentUrl = computed(() =>
    typeof props.modelValue === 'string' && props.modelValue ? props.modelValue : null,
  )

  const filename = ref<string | null>(null)

  watch(
    currentUrl,
    async (url) => {
      if (!url) {
        filename.value = null
        return
      }
      const fileId = extractFileId(url)
      if (!fileId) {
        filename.value = url.split('/').pop() ?? url
        return
      }
      try {
        const item = await filesApi.getById(fileId)
        filename.value = item?.filename ?? null
      } catch {
        filename.value = null
      }
    },
    { immediate: true },
  )

  function onSelect(result: AttachmentResult) {
    filename.value = result.filename
    emit('update:modelValue', result.url)
  }

  function remove() {
    emit('update:modelValue', null)
  }

  return { docContext, isDisabled, currentUrl, filename, onSelect, remove }
}
