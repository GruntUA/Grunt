<script setup lang="ts">
import { ref, computed, watch, inject } from 'vue'
import type { DocField } from '@/types'
import type { AttachmentResult } from '@/core/attachmentChannels/types'
import { Paperclip, X, ExternalLink } from '@lucide/vue'
import { cn } from '@/lib/utils'
import AttachPicker from './AttachPicker.vue'
import { filesApi } from '@/core/api/files'

const docContext = inject<{ doctype: string; getId: () => string | null } | null>('docContext', null)

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
    const params = new URL(url, window.location.origin).searchParams
    return params.get('file_id')
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
        isDisabled ? 'cursor-not-allowed opacity-50' : '',
        !currentUrl && !isDisabled ? 'cursor-pointer hover:border-ring/40' : '',
        error ? 'border-destructive' : '',
      )"
      @click="!isDisabled && !currentUrl && (pickerOpen = true)"
    >
      <Paperclip class="size-4 text-muted-foreground shrink-0" />

      <!-- File attached: filename opens the file in a new tab -->
      <a
        v-if="currentUrl"
        :href="currentUrl"
        target="_blank"
        rel="noopener noreferrer"
        class="flex-1 truncate text-primary hover:underline flex items-center gap-1"
        @click.stop
      >
        <span class="truncate">{{ filename ?? currentUrl }}</span>
        <ExternalLink class="size-3 shrink-0" />
      </a>

      <!-- No file: placeholder -->
      <span v-else class="flex-1 truncate text-muted-foreground">
        {{ field.placeholder || 'Прикріпити файл...' }}
      </span>

      <!-- Replace button (when file attached and not disabled) -->
      <button
        v-if="currentUrl && !isDisabled"
        type="button"
        title="Замінити файл"
        class="shrink-0 text-muted-foreground hover:text-foreground transition-colors"
        tabindex="-1"
        @click.stop="pickerOpen = true"
      >
        <Paperclip class="size-3.5" />
      </button>

      <!-- Remove button -->
      <button
        v-if="currentUrl && !isDisabled"
        type="button"
        title="Видалити вкладення"
        class="shrink-0 text-muted-foreground hover:text-destructive transition-colors"
        tabindex="-1"
        @click.stop="remove"
      >
        <X class="size-3.5" />
      </button>
    </div>

    <AttachPicker
      v-model:open="pickerOpen"
      :image-only="false"
      :attached-to-doctype="docContext?.doctype"
      :attached-to-id="docContext?.getId() ?? undefined"
      @select="onSelect"
    />
  </div>
</template>
