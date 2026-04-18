<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { DocField } from '@/types'
import type { AttachmentResult } from '@/core/attachmentChannels/types'
import { ImageIcon, X } from '@lucide/vue'
import { cn } from '@/lib/utils'
import AttachPicker from '@/components/fields/Attach/AttachPicker.vue'
import { filesApi } from '@/core/api/files'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: boolean
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const pickerOpen = ref(false)
const isDisabled = computed(() => !!(props.disabled || props.field.read_only))

const currentUrl = computed(() =>
  typeof props.modelValue === 'string' && props.modelValue ? props.modelValue : null
)

const filename = ref<string | null>(null)

function extractFileId(url: string): string | null {
  try {
    return new URL(url, window.location.origin).searchParams.get('file_id')
  } catch {
    const match = url.match(/[?&]file_id=([^&]+)/)
    return match ? match[1] : null
  }
}

watch(currentUrl, async (url) => {
  if (!url) { filename.value = null; return }
  const fileId = extractFileId(url)
  if (!fileId) { filename.value = url.split('/').pop() ?? url; return }
  try {
    const item = await filesApi.getById(fileId)
    filename.value = item?.filename ?? null
  } catch {
    filename.value = null
  }
}, { immediate: true })

function onSelect(result: AttachmentResult) {
  filename.value = result.filename
  emit('update:modelValue', result.url)
}

function remove(e: Event) {
  e.stopPropagation()
  emit('update:modelValue', null)
}
</script>

<template>
  <div>
    <div
      :class="cn(
        'flex h-9 w-full items-center gap-2 rounded-md border border-input bg-transparent px-3 text-sm shadow-sm transition-colors',
        'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
        isDisabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer hover:border-ring/40',
        error ? 'border-destructive' : '',
      )"
      @click="!isDisabled && (pickerOpen = true)"
    >
      <!-- Мініатюра 24px для зображень, інакше іконка -->
      <img
        v-if="currentUrl"
        :src="currentUrl"
        class="size-6 rounded object-cover shrink-0"
        alt=""
      />
      <ImageIcon v-else class="size-4 text-muted-foreground shrink-0" />

      <span class="flex-1 truncate" :class="currentUrl ? 'text-foreground' : 'text-muted-foreground'">
        {{ filename ?? (field.placeholder || 'Прикріпити зображення...') }}
      </span>
      <button
        v-if="currentUrl && !isDisabled"
        type="button"
        class="shrink-0 text-muted-foreground hover:text-foreground transition-colors"
        tabindex="-1"
        @click="remove"
      >
        <X class="size-3.5" />
      </button>
    </div>

    <AttachPicker
      v-model:open="pickerOpen"
      :image-only="true"
      @select="onSelect"
    />
  </div>
</template>
