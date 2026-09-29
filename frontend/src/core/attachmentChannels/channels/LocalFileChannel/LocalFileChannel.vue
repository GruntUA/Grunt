<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref } from 'vue'
import type { AttachmentResult, AttachChannelProps, AttachChannelEmits } from '@/core/attachmentChannels/types'
import { filesApi } from '@/core/api/files'
import { Upload, AlertCircle } from '@lucide/vue'

const { t } = useI18n()

const props = defineProps<AttachChannelProps>()
const emit = defineEmits<AttachChannelEmits>()

const isDragging = ref(false)
const isUploading = ref(false)
const uploadProgress = ref(0)
const error = ref('')
const fileInput = ref<HTMLInputElement>()

async function uploadFiles(files: File[]) {
  if (!props.multiple) files = files.slice(0, 1)
  if (!files.length) return
  error.value = ''
  isUploading.value = true
  uploadProgress.value = 0
  try {
    const results: AttachmentResult[] = []
    for (const [i, file] of files.entries()) {
      const item = await filesApi.upload(file, {
        attachedToDoctype: props.attachedToDoctype,
        attachedToId: props.attachedToId,
      })
      results.push({ url: item.url, filename: item.filename, contentType: item.content_type, fileItem: item })
      uploadProgress.value = Math.round(((i + 1) / files.length) * 100)
    }
    if (props.multiple) emit('selectMany', results)
    else emit('select', results[0])
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : t('Upload error')
  } finally {
    isUploading.value = false
  }
}

function onDrop(e: DragEvent) {
  isDragging.value = false
  uploadFiles(Array.from(e.dataTransfer?.files ?? []))
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  uploadFiles(Array.from(input.files ?? []))
  input.value = ''
}
</script>

<template>
  <div
    class="m-3 flex flex-col items-center justify-center rounded-lg border-2 border-dashed transition-colors cursor-pointer min-h-[300px] gap-3"
    :class="isDragging ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/40'"
    @dragover.prevent="isDragging = true"
    @dragleave="isDragging = false"
    @drop.prevent="onDrop"
    @click="fileInput?.click()"
  >
    <template v-if="isUploading">
      <div class="w-48 bg-muted rounded-full h-1.5">
        <div class="bg-primary h-1.5 rounded-full transition-all" :style="{ width: uploadProgress + '%' }" />
      </div>
      <p class="text-muted-foreground">{{ t('Uploading...') }}</p>
    </template>
    <template v-else>
      <Upload class="size-8 text-muted-foreground/50" />
      <div class="text-center">
        <p class="text-foreground">{{ t('Drop a file or') }} <span class="text-primary font-medium">{{ t('click to choose') }}</span></p>
        <p v-if="imageOnly" class="text-muted-foreground mt-1">{{ t('Images only') }}</p>
      </div>
    </template>

    <div v-if="error" class="flex items-center gap-1.5 text-destructive" @click.stop>
      <AlertCircle class="size-3.5 shrink-0" />
      {{ error }}
    </div>

    <input
      ref="fileInput"
      type="file"
      class="sr-only"
      :accept="imageOnly ? 'image/*' : undefined"
      :multiple="multiple"
      @change="onFileChange"
    />
  </div>
</template>
