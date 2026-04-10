<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DocField } from '@/types'
import client from '@/core/api/client'
import { ImageIcon, X } from 'lucide-vue-next'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const { t } = useI18n()
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
  <div>
    <!-- Current image -->
    <div v-if="currentUrl()" class="relative inline-block">
      <img :src="currentUrl()!" class="max-h-48 rounded-lg border border-border object-contain" />
      <button
        v-if="!disabled"
        type="button"
        class="absolute top-1 right-1 bg-background rounded-full w-6 h-6 flex items-center justify-center text-destructive shadow-sm border border-border hover:bg-destructive hover:text-destructive-foreground transition-colors"
        @click="emit('update:modelValue', null)"
      >
        <X class="size-3.5" />
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
      <div v-if="isUploading" class="text-sm text-muted-foreground">{{ t('Loading...') }}</div>
      <div v-else class="flex flex-col items-center gap-1">
        <ImageIcon class="size-8 text-muted-foreground/50" />
        <p class="text-sm text-muted-foreground">Перетягни зображення або <span class="text-primary font-medium">клікни</span></p>
      </div>
      <input ref="fileInput" type="file" accept="image/*" class="sr-only" :disabled="disabled" @change="onFileChange" />
    </div>
  </div>
</template>
