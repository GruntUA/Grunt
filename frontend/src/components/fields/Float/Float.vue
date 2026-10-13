<script setup lang="ts">
import type { DocField } from '@/types'
import {
  NumberField, NumberFieldContent, NumberFieldDecrement, NumberFieldIncrement, NumberFieldInput,
} from '@/components/ui/number-field'
import { fieldNumber, localeTag, onDecimalKey } from '@/core/composables/useNumberField'

defineProps<{
  field: DocField
  modelValue: number | null | undefined
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: number | null] }>()

const formatOptions: Intl.NumberFormatOptions = { maximumFractionDigits: 10 }
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
    @update:model-value="emit('update:modelValue', fieldNumber($event))"
  >
    <NumberFieldContent>
      <NumberFieldDecrement />
      <NumberFieldInput
        :placeholder="field.placeholder ?? '0.0'"
        :required="field.required"
        :aria-invalid="error ? true : undefined"
        :class="['tabular-nums', field.bold && 'font-medium']"
        @keydown="onDecimalKey"
      />
      <NumberFieldIncrement />
    </NumberFieldContent>
  </NumberField>
</template>
