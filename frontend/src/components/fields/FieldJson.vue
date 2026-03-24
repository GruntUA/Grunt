<script setup lang="ts">
import { ref, watch } from 'vue'
import type { DocField } from '@/types'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()
const localError = ref<string | null>(null)

function formatValue(v: unknown): string {
  if (v === null || v === undefined || v === '') return ''
  if (typeof v === 'string') return v
  try { return JSON.stringify(v, null, 2) } catch { return String(v) }
}

const text = ref(formatValue(props.modelValue))

watch(() => props.modelValue, (v) => { text.value = formatValue(v) })

function onInput(val: string) {
  text.value = val
  localError.value = null
  if (!val.trim()) {
    emit('update:modelValue', null)
    return
  }
  try {
    emit('update:modelValue', JSON.parse(val))
  } catch {
    // defer error to blur
  }
}

function onBlur() {
  if (!text.value.trim()) return
  try {
    const parsed = JSON.parse(text.value)
    text.value = JSON.stringify(parsed, null, 2)
    localError.value = null
  } catch {
    localError.value = 'Невалідний JSON'
  }
}
</script>

<template>
  <div class="flex flex-col gap-1">
    <textarea
      :value="text"
      :disabled="disabled || field.read_only"
      rows="6"
      class="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm font-mono ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-y disabled:bg-muted disabled:cursor-not-allowed"
      :class="{ 'border-destructive focus-visible:ring-destructive': error || localError }"
      @input="onInput(($event.target as HTMLTextAreaElement).value)"
      @blur="onBlur"
    />
    <p v-if="localError" class="text-xs text-destructive">{{ localError }}</p>
  </div>
</template>
