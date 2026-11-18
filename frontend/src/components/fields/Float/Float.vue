<script setup lang="ts">
import { computed } from 'vue'
import type { DocField } from '@/types'
import { roundToPrecision } from '@/core/numbers'
import { NumberField, NumberFieldContent, NumberFieldInput } from '@/components/ui/number-field'
import { fieldNumber, localeTag, onDecimalKey } from '@/core/composables/useNumberField'

const props = defineProps<{
  field: DocField
  modelValue: number | null | undefined
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: number | null] }>()

// A precision fixes the decimals (and rounds like the server); without it - up to 10.
const formatOptions = computed<Intl.NumberFormatOptions>(() => {
  const p = props.field.precision
  const digits = p == null ? { maximumFractionDigits: 10 } : { minimumFractionDigits: p, maximumFractionDigits: p }
  return { ...{ maximumFractionDigits: 10 }, ...digits }
})
const toPrecision = (n: number) => roundToPrecision(n, props.field.precision)
</script>

<template>
  <!-- The wheel doesn't change a focused value: silent data corruption on scroll. -->
  <NumberField
    :model-value="modelValue ?? null"
    :locale="localeTag()"
    :format-options="formatOptions"
    :step-snapping="false"
    :min="field.min_value ?? undefined"
    :max="field.max_value ?? undefined"
    :disabled="disabled || field.read_only"
    disable-wheel-change
    @update:model-value="emit('update:modelValue', fieldNumber($event, toPrecision))"
  >
    <NumberFieldContent>
      <NumberFieldInput
        :placeholder="field.placeholder ?? '0.0'"
        :required="field.required"
        :aria-invalid="error ? true : undefined"
        :class="['tabular-nums', field.bold && 'font-medium']"
        @keydown="onDecimalKey"
      />
    </NumberFieldContent>
  </NumberField>
</template>
