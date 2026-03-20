<script setup lang="ts">
import { ref } from 'vue'
import type { DocField } from '@/types'
import client from '@/core/api/client'

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
  <div class="flex flex-col gap-1">
    <label class="text-sm font-medium text-[--grunt-text-primary]">
      {{ field.label }}<span v-if="field.required" class="text-[--grunt-danger] ml-0.5">*</span>
    </label>

    <!-- Current file -->
    <div v-if="currentUrl()" class="flex items-center gap-2 p-2 bg-[--grunt-surface-secondary] rounded-[--grunt-radius-sm] border border-[--grunt-border]">
      <span class="text-sm flex-1 truncate">📎 {{ fileName(currentUrl()!) }}</span>
      <a :href="currentUrl()!" target="_blank" class="text-xs text-[--grunt-primary] hover:underline">Відкрити</a>
      <button v-if="!disabled" type="button" class="text-[--grunt-text-muted] hover:text-[--grunt-danger]" @click="removeFile">×</button>
    </div>

    <!-- Upload zone -->
    <div
      v-else
      class="border-2 border-dashed rounded-[--grunt-radius-md] p-6 text-center transition-colors cursor-pointer"
      :class="isDragging ? 'border-[--grunt-primary] bg-[--grunt-primary-light]' : 'border-[--grunt-border] hover:border-[--grunt-primary]'"
      @dragover.prevent="isDragging = true"
      @dragleave="isDragging = false"
      @drop.prevent="onDrop"
      @click="fileInput?.click()"
    >
      <div v-if="isUploading" class="flex flex-col items-center gap-2">
        <div class="w-full bg-[--grunt-border] rounded-full h-1.5">
          <div class="bg-[--grunt-primary] h-1.5 rounded-full transition-all" :style="{ width: uploadProgress + '%' }" />
        </div>
        <p class="text-xs text-[--grunt-text-muted]">{{ uploadProgress }}%</p>
      </div>
      <div v-else>
        <p class="text-sm text-[--grunt-text-secondary]">Перетягни файл або <span class="text-[--grunt-primary]">клікни для вибору</span></p>
      </div>
      <input ref="fileInput" type="file" class="sr-only" :disabled="disabled" @change="onFileChange" />
    </div>

    <p v-if="error" class="text-xs text-[--grunt-danger]">{{ error }}</p>
  </div>
</template>
