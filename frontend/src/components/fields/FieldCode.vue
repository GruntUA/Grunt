<script setup lang="ts">
import type { DocField } from '@/types'

defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()
</script>

<template>
  <textarea
    :value="String(modelValue ?? '')"
    :disabled="disabled || field.read_only"
    rows="8"
    spellcheck="false"
    class="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm font-mono ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:border-ring resize-y disabled:bg-muted disabled:text-muted-foreground disabled:cursor-not-allowed whitespace-pre"
    :class="{ 'border-destructive focus-visible:ring-destructive': error }"
    @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
  />
</template>
