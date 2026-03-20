<script setup lang="ts">
import { ref, watch } from 'vue'
import { useId } from 'vue'
import type { DocField } from '@/types'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()
const id = useId()
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
    <label :for="id" class="text-sm font-medium text-[--grunt-text-primary]">
      {{ field.label }}<span v-if="field.required" class="text-[--grunt-danger] ml-0.5">*</span>
    </label>
    <textarea
      :id="id"
      :value="text"
      :disabled="disabled || field.read_only"
      rows="6"
      class="w-full rounded-[--grunt-radius-sm] border border-[--grunt-border] px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-[--grunt-primary]/30 focus:border-[--grunt-primary] resize-y disabled:bg-[--grunt-surface-secondary]"
      :class="{ 'border-[--grunt-danger]': error || localError }"
      @input="onInput(($event.target as HTMLTextAreaElement).value)"
      @blur="onBlur"
    />
    <p v-if="error || localError" class="text-xs text-[--grunt-danger]">{{ error ?? localError }}</p>
    <p v-else-if="field.description" class="text-xs text-[--grunt-text-muted]">{{ field.description }}</p>
  </div>
</template>
