<script setup lang="ts">
/**
 * «Attach a file» - the personal folders in a FileExplorer: pick a file, or
 * bring one in first through «Create» (computer, camera, a link) or the
 * search box (any file you can see). Opens on the file the field / link
 * points at now, in its folder, selected.
 */
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { docsApi } from '@/core/api/docs'
import type { FileItem } from '@/core/api/files'
import { extractFileId } from '@/core/fileUtils'
import FileExplorer from '@/components/files/FileExplorer.vue'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import type { AttachmentResult } from './attachment'

const props = defineProps<{
  open: boolean
  imageOnly?: boolean
  /** Return several files at once. */
  multiple?: boolean
  /** URL stored in the field now - the picker opens on that file. */
  currentUrl?: string | null
  /** Dialog title instead of «Attach a file» / «Attach an image». */
  title?: string
  /** Confirm button label (e.g. «Insert link»). */
  actionLabel?: string
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  select: [result: AttachmentResult]
  selectMany: [results: AttachmentResult[]]
}>()

const { t } = useI18n()
const selection = ref<FileItem[]>([])

// Where to open: the folder of the current file, with it selected.
const ready = ref(false)
const startFolder = ref<string | null>(null)
const currentFile = ref<string | null>(null)

watch(() => props.open, async (open) => {
  ready.value = false
  selection.value = []
  if (!open) return
  currentFile.value = props.currentUrl ? extractFileId(props.currentUrl) : null
  startFolder.value = null
  if (currentFile.value) {
    const doc = await docsApi.get('File', currentFile.value).catch(() => null)
    startFolder.value = (doc?.folder as string | null | undefined) ?? null
  }
  ready.value = true
}, { immediate: true })

function toResult(item: FileItem): AttachmentResult {
  return { url: item.url, filename: item.filename, contentType: item.content_type, fileItem: item }
}

function attach(items: FileItem[]) {
  if (!items.length) return
  if (props.multiple) emit('selectMany', items.map(toResult))
  else emit('select', toResult(items[0]))
  emit('update:open', false)
}
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="flex h-[min(680px,88vh)] flex-col gap-0 overflow-hidden p-0 sm:max-w-5xl">
      <DialogHeader class="shrink-0 px-4 pt-4 pb-3">
        <DialogTitle class="font-semibold">
          {{ title ?? (imageOnly ? t('Attach an image') : t('Attach a file')) }}
        </DialogTitle>
      </DialogHeader>
      <FileExplorer v-if="ready" mode="file" :multiple="multiple" :image-only="imageOnly"
        :folder="startFolder" :focus-file="startFolder ? currentFile : null"
        :view="imageOnly ? 'tiles' : 'details'"
        @update:selection="selection = $event" @activate="attach([$event])">
        <template #footer>
          <Button :disabled="!selection.length" @click="attach(selection)">
            {{ actionLabel ?? (selection.length > 1 ? t('Attach ({n})', { n: selection.length }) : t('Attach')) }}
          </Button>
        </template>
      </FileExplorer>
    </DialogContent>
  </Dialog>
</template>
