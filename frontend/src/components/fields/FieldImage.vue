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
const fileInput = ref<HTMLInputElement>()

const currentUrl = () => typeof props.modelValue === 'string' ? props.modelValue : null

async function uploadFile(file: File) {
  isUploading.value = true
  const fd = new FormData()
  fd.append('file', file)
  try {
    const resp = await client.post('/api/v1/files/', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
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
</script>

<template>
  <div class="flex flex-col gap-1">
    <label class="text-sm font-medium text-[--grunt-text-primary]">
      {{ field.label }}<span v-if="field.required" class="text-[--grunt-danger] ml-0.5">*</span>
    </label>

    <!-- Current image -->
    <div v-if="currentUrl()" class="relative inline-block">
      <img :src="currentUrl()!" class="max-h-48 rounded-[--grunt-radius-md] border border-[--grunt-border] object-contain" />
      <button
        v-if="!disabled"
        type="button"
        class="absolute top-1 right-1 bg-white rounded-full w-5 h-5 flex items-center justify-center text-[--grunt-danger] shadow hover:bg-[--grunt-danger] hover:text-white transition-colors text-xs"
        @click="emit('update:modelValue', null)"
      >×</button>
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
      <div v-if="isUploading" class="text-sm text-[--grunt-text-muted]">Завантаження...</div>
      <div v-else>
        <p class="text-2xl mb-1">🖼</p>
        <p class="text-sm text-[--grunt-text-secondary]">Перетягни зображення або <span class="text-[--grunt-primary]">клікни</span></p>
      </div>
      <input ref="fileInput" type="file" accept="image/*" class="sr-only" :disabled="disabled" @change="onFileChange" />
    </div>

    <p v-if="error" class="text-xs text-[--grunt-danger]">{{ error }}</p>
  </div>
</template>
