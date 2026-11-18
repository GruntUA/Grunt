<script setup lang="ts">
import { computed } from 'vue'
import type { DocField } from '@/types'
import { NumberField, NumberFieldContent, NumberFieldInput } from '@/components/ui/number-field'
import { currencyCode, currencyPrecision } from '@/core/currency'
import { roundToPrecision } from '@/core/numbers'
import { fieldNumber, localeTag, onDecimalKey } from '@/core/composables/useNumberField'

const props = defineProps<{
  field: DocField
  modelValue: number | null | undefined
  disabled?: boolean
  error?: string
  doc?: Record<string, unknown>
}>()

const emit = defineEmits<{ 'update:modelValue': [value: number | null] }>()

// The currency is shown by the formatter (`1 234,50 ₴`); without a code - the
// field's decimals (precision, two by default).
const precision = computed(() => currencyPrecision(props.field))
const formatOptions = computed<Intl.NumberFormatOptions>(() => {
  const code = currencyCode(props.field, props.doc)
  const plain = { minimumFractionDigits: precision.value, maximumFractionDigits: precision.value }
  if (!code) return plain
  try {
    new Intl.NumberFormat(localeTag(), { style: 'currency', currency: code })
    return { ...plain, style: 'currency', currency: code, currencyDisplay: 'narrowSymbol' }
  } catch {
    return plain // unknown code
  }
})

// Rounded like the server stores it (site rounding method, core/numbers.ts).
const toPrecision = (n: number) => roundToPrecision(n, precision.value)
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
    @update:model-value="emit('update:modelValue', fieldNumber($event, toPrecision))"
  >
    <NumberFieldContent>
      <NumberFieldInput
        :placeholder="field.placeholder ?? '0.00'"
        :required="field.required"
        :aria-invalid="error ? true : undefined"
        :class="['tabular-nums', field.bold && 'font-medium']"
        @keydown="onDecimalKey"
      />
    </NumberFieldContent>
  </NumberField>
</template>
