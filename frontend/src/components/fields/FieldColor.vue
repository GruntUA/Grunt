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
  <div class="flex flex-col gap-1">
    <label :for="id" class="text-sm font-medium text-[--grunt-text-primary]">
      {{ field.label }}<span v-if="field.required" class="text-[--grunt-danger] ml-0.5">*</span>
    </label>
    <div class="flex items-center gap-2">
      <input
        :id="id"
        type="color"
        :value="hex"
        :disabled="disabled || field.read_only"
        class="h-9 w-12 rounded border border-[--grunt-border] cursor-pointer p-0.5"
        @input="onColorChange(($event.target as HTMLInputElement).value)"
      />
      <input
        type="text"
        :value="hex"
        :disabled="disabled || field.read_only"
        maxlength="7"
        class="flex-1 rounded-[--grunt-radius-sm] border border-[--grunt-border] px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-[--grunt-primary]/30 focus:border-[--grunt-primary] disabled:bg-[--grunt-surface-secondary]"
        :class="{ 'border-[--grunt-danger]': error }"
        @input="onHexInput(($event.target as HTMLInputElement).value)"
      />
    </div>
    <p v-if="error" class="text-xs text-[--grunt-danger]">{{ error }}</p>
  </div>
</template>
