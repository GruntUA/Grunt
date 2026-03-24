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
const hex = ref(String(props.modelValue ?? '#000000'))

watch(() => props.modelValue, (v) => { hex.value = String(v ?? '#000000') })

function onColorChange(val: string) {
  hex.value = val
  emit('update:modelValue', val)
}

function onHexInput(val: string) {
  hex.value = val
  if (/^#[0-9A-Fa-f]{6}$/.test(val)) {
    emit('update:modelValue', val)
  }
}
</script>

<template>
  <div class="flex items-center gap-2">
    <input
      type="color"
      :value="hex"
      :disabled="disabled || field.read_only"
      class="h-9 w-12 rounded-md border border-input cursor-pointer p-0.5"
      @input="onColorChange(($event.target as HTMLInputElement).value)"
    />
    <input
      type="text"
      :value="hex"
      :disabled="disabled || field.read_only"
      maxlength="7"
      class="flex-1 rounded-md border border-input bg-transparent px-3 py-2 text-sm font-mono ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:bg-muted disabled:cursor-not-allowed"
      :class="{ 'border-destructive focus-visible:ring-destructive': error }"
      @input="onHexInput(($event.target as HTMLInputElement).value)"
    />
  </div>
</template>
