<script setup lang="ts">
import { computed } from 'vue'
import type { DocField } from '@/types'
import { NumberField, NumberFieldContent, NumberFieldInput } from '@/components/ui/number-field'
import { currencyCode } from '@/core/currency'
import { fieldNumber, localeTag, onDecimalKey } from '@/core/composables/useNumberField'

const props = defineProps<{
  field: DocField
  modelValue: number | null | undefined
  disabled?: boolean
  error?: string
  doc?: Record<string, unknown>
}>()

const emit = defineEmits<{ 'update:modelValue': [value: number | null] }>()

// The currency is shown by the formatter (`1 234,50 ₴`); without a code - two decimals.
const formatOptions = computed<Intl.NumberFormatOptions>(() => {
  const code = currencyCode(props.field, props.doc)
  const plain = { minimumFractionDigits: 2, maximumFractionDigits: 2 }
  if (!code) return plain
  try {
    new Intl.NumberFormat(localeTag(), { style: 'currency', currency: code })
    return { ...plain, style: 'currency', currency: code, currencyDisplay: 'narrowSymbol' }
  } catch {
    return plain // unknown code
  }
})

const toCents = (n: number) => Math.round(n * 100) / 100
</script>

<template>
  <!-- No +/- buttons: stepping an amount by 1 is rarely what anyone wants.
       The wheel doesn't change a focused value: silent data corruption on scroll. -->
  <NumberField
    :model-value="modelValue ?? null"
    :locale="localeTag()"
    :format-options="formatOptions"
    :step-snapping="false"
    :min="field.min_value ?? undefined"
    :max="field.max_value ?? undefined"
    :disabled="disabled || field.read_only"
    disable-wheel-change
    @update:model-value="emit('update:modelValue', fieldNumber($event, toCents))"
  >
    <NumberFieldContent>
      <NumberFieldInput
        :placeholder="field.placeholder ?? '0.00'"
        :required="field.required"
        :aria-invalid="error ? true : undefined"
        :class="['text-right tabular-nums', field.bold && 'font-medium']"
        @keydown="onDecimalKey"
      />
    </NumberFieldContent>
  </NumberField>
</template>
