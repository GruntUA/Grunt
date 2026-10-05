<script setup lang="ts">
import { computed } from 'vue'
import type { DocField } from '@/types'
import { Input } from '@/components/ui/input'
import { currencyCode, currencySymbol } from '@/core/currency'

const props = defineProps<{
  field: DocField
  modelValue: number | null | undefined
  disabled?: boolean
  error?: string
  doc?: Record<string, unknown>
}>()

const emit = defineEmits<{ 'update:modelValue': [value: number | null] }>()

const symbol = computed(() => currencySymbol(currencyCode(props.field, props.doc)))

function onUpdate(v: string | number) {
  if (v === '' || v == null) return emit('update:modelValue', null)
  const n = Number(v)
  emit('update:modelValue', Number.isFinite(n) ? Math.round(n * 100) / 100 : null)
}

// A focused number input changes its value when you scroll over it - silent
// data corruption. Swallow the wheel while focused; page scroll still works
// when the field isn't focused.
function onWheel(e: WheelEvent) {
  if (document.activeElement === e.target) e.preventDefault()
}
</script>

<template>
  <div class="relative">
    <Input
      type="number"
      step="0.01"
      inputmode="decimal"
      :model-value="modelValue ?? ''"
      :placeholder="field.placeholder ?? '0.00'"
      :required="field.required"
      :disabled="disabled || field.read_only"
      :min="field.min_value"
      :max="field.max_value"
      :aria-invalid="error ? true : undefined"
      :class="['w-full tabular-nums', symbol && 'pr-10', field.bold && 'font-medium']"
      @wheel="onWheel"
      @update:model-value="onUpdate"
    />
    <span
      v-if="symbol"
      class="pointer-events-none absolute inset-y-0 right-2.5 flex items-center text-muted-foreground"
    >{{ symbol }}</span>
  </div>
</template>
