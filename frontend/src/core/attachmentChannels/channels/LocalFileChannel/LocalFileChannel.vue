<script setup lang="ts">
import { ref } from 'vue'
import type { AttachmentResult } from '@/core/attachmentChannels/types'
import { filesApi } from '@/core/api/files'
import { Upload, AlertCircle } from '@lucide/vue'

const props = defineProps<{ imageOnly: boolean }>()
const emit = defineEmits<{ select: [result: AttachmentResult] }>()

const isDragging = ref(false)
const isUploading = ref(false)
const uploadProgress = ref(0)
const error = ref('')
const fileInput = ref<HTMLInputElement>()

async function uploadFile(file: File) {
  error.value = ''
  isUploading.value = true
  uploadProgress.value = 0
  try {
    const item = await filesApi.upload(file)
    emit('select', {
      url: item.url,
      filename: item.filename,
      contentType: item.content_type,
      fileItem: item,
    })
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Помилка завантаження'
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
      <p class="text-sm text-muted-foreground">Завантаження...</p>
    </template>
    <template v-else>
      <Upload class="size-8 text-muted-foreground/50" />
      <div class="text-center">
        <p class="text-sm text-foreground">Перетягни файл або <span class="text-primary font-medium">клікни для вибору</span></p>
        <p v-if="imageOnly" class="text-xs text-muted-foreground mt-1">Тільки зображення</p>
      </div>
    </template>

    <div v-if="error" class="flex items-center gap-1.5 text-xs text-destructive" @click.stop>
      <AlertCircle class="size-3.5 shrink-0" />
      {{ error }}
    </div>

    <input
      ref="fileInput"
      type="file"
      class="sr-only"
      :accept="imageOnly ? 'image/*' : undefined"
      @change="onFileChange"
    />
  </div>
</template>
