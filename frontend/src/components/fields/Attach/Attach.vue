<script setup lang="ts">
import { ref } from 'vue'
import type { DocField } from '@/types'
import client from '@/core/api/client'
import { Paperclip, ExternalLink, X, Upload } from '@lucide/vue'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const isDragging = ref(false)
const isUploading = ref(false)
const uploadProgress = ref(0)
const fileInput = ref<HTMLInputElement>()

const currentUrl = () => typeof props.modelValue === 'string' ? props.modelValue : null

async function uploadFile(file: File) {
  isUploading.value = true
  uploadProgress.value = 0
  const fd = new FormData()
  fd.append('file', file)
  try {
    const resp = await client.post('/api/v1/files/', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (e) => {
        uploadProgress.value = Math.round((e.loaded / (e.total ?? 1)) * 100)
      },
    })
    emit('update:modelValue', resp.data.data?.url ?? resp.data.url)
  } catch {
    // upload failed
  } finally {
    isUploading.value = false
  }
}

function onDrop(e: DragEvent) {
  isDragging.value = false
  const file = e.dataTransfer?.files[0]
  if (file) uploadFile(file)
}

function onFileChange(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) uploadFile(file)
}

function removeFile() {
  emit('update:modelValue', null)
  if (fileInput.value) fileInput.value.value = ''
}

function fileName(url: string) {
  return url.split('/').pop() ?? url
}
</script>

<template>
  <div>
    <!-- Current file -->
    <div v-if="currentUrl()" class="flex items-center gap-2 p-2.5 bg-muted rounded-lg border border-border">
      <Paperclip class="size-4 text-muted-foreground shrink-0" />
      <span class="text-sm flex-1 truncate">{{ fileName(currentUrl()!) }}</span>
      <a :href="currentUrl()!" target="_blank" class="text-xs text-primary hover:underline inline-flex items-center gap-1">
        <ExternalLink class="size-3" />
        Відкрити
      </a>
      <button v-if="!disabled" type="button" class="text-muted-foreground hover:text-destructive transition-colors" @click="removeFile">
        <X class="size-4" />
      </button>
    </div>

    <!-- Upload zone -->
    <div
      v-else
      class="border-2 border-dashed rounded-lg p-6 text-center transition-colors cursor-pointer"
      :class="isDragging ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/50'"
      @dragover.prevent="isDragging = true"
      @dragleave="isDragging = false"
      @drop.prevent="onDrop"
      @click="fileInput?.click()"
    >
      <div v-if="isUploading" class="flex flex-col items-center gap-2">
        <div class="w-full bg-muted rounded-full h-1.5">
          <div class="bg-primary h-1.5 rounded-full transition-all" :style="{ width: uploadProgress + '%' }" />
        </div>
        <p class="text-xs text-muted-foreground">{{ uploadProgress }}%</p>
      </div>
      <div v-else class="flex flex-col items-center gap-1">
        <Upload class="size-5 text-muted-foreground" />
        <p class="text-sm text-muted-foreground">Перетягни файл або <span class="text-primary font-medium">клікни для вибору</span></p>
      </div>
      <input ref="fileInput" type="file" class="sr-only" :disabled="disabled" @change="onFileChange" />
    </div>
  </div>
</template>
