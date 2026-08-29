<script setup lang="ts">
import type { DocField } from '@/types'

defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

function autoResize(el: HTMLTextAreaElement) {
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}
</script>

<template>
  <textarea
    :value="String(modelValue ?? '')"
    :placeholder="field.placeholder ?? ''"
    :disabled="disabled || field.read_only"
    rows="3"
    class="w-full rounded-md border border-input bg-transparent px-3 py-2 text-foreground placeholder:text-muted-foreground ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:border-ring resize-none overflow-hidden disabled:bg-muted disabled:text-muted-foreground disabled:cursor-not-allowed"
    :class="{ 'border-destructive focus-visible:ring-destructive': error }"
    @input="(e) => { emit('update:modelValue', (e.target as HTMLTextAreaElement).value); autoResize(e.target as HTMLTextAreaElement) }"
    @focus="(e) => autoResize(e.target as HTMLTextAreaElement)"
  />
</template>
