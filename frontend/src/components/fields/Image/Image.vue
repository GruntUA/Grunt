<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { BaseFieldProps } from '@/types'
import { ImageIcon, X } from '@lucide/vue'
import { cn } from '@/lib/utils'
import AttachPicker from '@/components/fields/Attach/AttachPicker.vue'
import { useAttachmentField } from '@/components/fields/Attach/useAttachmentField'

const props = defineProps<BaseFieldProps>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const { t } = useI18n()
const { docContext, isDisabled, currentUrl, filename, onSelect, remove } = useAttachmentField(props, emit)

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
        isDisabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer hover:border-ring/40',
        error ? 'border-destructive' : '',
      )"
      :role="isDisabled || currentUrl ? undefined : 'button'"
      :tabindex="isDisabled ? undefined : 0"
      :aria-label="currentUrl ? t('Replace image') : (field.placeholder || t('Attach an image…'))"
      :aria-invalid="error ? true : undefined"
      @click="openPicker"
      @keydown.enter.prevent="openPicker"
      @keydown.space.prevent="openPicker"
    >
      <img
        v-if="currentUrl"
        :src="currentUrl"
        class="size-6 shrink-0 rounded object-cover"
        :alt="filename ?? ''"
      />
      <ImageIcon v-else class="size-4 shrink-0 text-muted-foreground" />

      <span class="flex-1 truncate" :class="currentUrl ? 'text-foreground' : 'text-muted-foreground'">
        {{ filename ?? (field.placeholder || t('Attach an image…')) }}
      </span>

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
      :image-only="true"
      :attached-to-doctype="docContext?.doctype"
      :attached-to-id="docContext?.getId() ?? undefined"
      :current-url="currentUrl"
      @select="onSelect"
    />
  </div>
</template>
