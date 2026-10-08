<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { BaseFieldProps } from '@/types'
import { Paperclip, X, ExternalLink, Link2 } from '@lucide/vue'
import { cn } from '@/lib/utils'
import AttachPicker from './AttachPicker.vue'
import { useAttachmentField } from './useAttachmentField'

const props = defineProps<BaseFieldProps>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const { t } = useI18n()
const { isDisabled, currentUrl, isExternal, filename, onSelect, remove } = useAttachmentField(props, emit)

const pickerOpen = ref(false)

function openPicker() {
  if (!isDisabled.value) pickerOpen.value = true
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
      :role="!currentUrl && !isDisabled ? 'button' : undefined"
      :tabindex="!currentUrl && !isDisabled ? 0 : undefined"
      :aria-label="!currentUrl ? (field.placeholder || t('Attach a file…')) : undefined"
      :aria-invalid="error ? true : undefined"
      @click="!isDisabled && !currentUrl && openPicker()"
      @keydown.enter.prevent="!currentUrl && openPicker()"
      @keydown.space.prevent="!currentUrl && openPicker()"
    >
      <Link2 v-if="isExternal" class="size-4 shrink-0 text-muted-foreground" />
      <Paperclip v-else class="size-4 shrink-0 text-muted-foreground" />

      <!-- File attached: filename opens the file in a new tab; a link shows its address on hover -->
      <a
        v-if="currentUrl"
        :href="currentUrl"
        :title="isExternal ? currentUrl : undefined"
        target="_blank"
        rel="noopener noreferrer"
        class="flex min-w-0 flex-1 items-center gap-1 truncate text-primary hover:underline"
        @click.stop
      >
        <span class="truncate">{{ filename ?? currentUrl }}</span>
        <ExternalLink class="size-3 shrink-0" />
      </a>

      <span v-else class="flex-1 truncate text-muted-foreground">
        {{ field.placeholder || t('Attach a file…') }}
      </span>

      <button
        v-if="currentUrl && !isDisabled"
        type="button"
        :title="t('Replace file')"
        :aria-label="t('Replace file')"
        class="shrink-0 text-muted-foreground transition-colors hover:text-foreground"
        @click.stop="openPicker"
      >
        <Paperclip class="size-3.5" />
      </button>

      <button
        v-if="currentUrl && !isDisabled"
        type="button"
        :title="t('Remove attachment')"
        :aria-label="t('Remove attachment')"
        class="shrink-0 text-muted-foreground transition-colors hover:text-destructive"
        @click.stop="remove"
      >
        <X class="size-3.5" />
      </button>
    </div>

    <AttachPicker
      v-model:open="pickerOpen"
      :image-only="false"
      :current-url="currentUrl"
      @select="onSelect"
    />
  </div>
</template>
