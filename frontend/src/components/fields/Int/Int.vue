<script setup lang="ts">
import { computed } from 'vue'
import i18n from '@/plugins/i18n'
import type { DocField } from '@/types'
import {
  NumberField, NumberFieldContent, NumberFieldDecrement, NumberFieldIncrement, NumberFieldInput,
} from '@/components/ui/number-field'
import { fieldNumber, localeTag, onDecimalKey } from '@/core/composables/useNumberField'
import { formatBytes, isBytesField } from '@/core/bytes'
import { formatNumber } from '@/core/currency'

const props = defineProps<{
  field: DocField
  modelValue: number | null | undefined
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: number | null] }>()

const formatOptions: Intl.NumberFormatOptions = { maximumFractionDigits: 0 }

// `options: "Bytes"`: a read-only size reads as `14.2 MB` (exact count on hover);
// an editable one keeps the number input with the size next to it.
const isBytes = computed(() => isBytesField(props.field))
const isReadOnly = computed(() => !!(props.disabled || props.field.read_only))
const hasValue = computed(() => props.modelValue !== null && props.modelValue !== undefined)
</script>

<template>
  <div
    v-if="isBytes && isReadOnly"
    class="flex h-9 w-full items-center rounded-md border border-input bg-muted/40 px-3 text-sm tabular-nums"
    :class="field.bold && 'font-medium'"
    :title="hasValue ? `${formatNumber(Number(modelValue))} ${i18n.global.t('B')}` : undefined"
  >
    <span v-if="hasValue">{{ formatBytes(Number(modelValue)) }}</span>
    <span v-else class="text-muted-foreground">—</span>
  </div>
  <!-- The wheel doesn't change a focused value: silent data corruption on scroll. -->
  <div v-else class="flex items-center gap-2">
    <NumberField
      class="flex-1"
      :model-value="modelValue ?? null"
      :locale="localeTag()"
      :format-options="formatOptions"
      :step-snapping="false"
      :min="field.min_value ?? undefined"
      :max="field.max_value ?? undefined"
      :disabled="disabled || field.read_only"
      disable-wheel-change
      @update:model-value="emit('update:modelValue', fieldNumber($event, Math.trunc))"
    >
      <NumberFieldContent>
        <NumberFieldDecrement />
        <NumberFieldInput
          :placeholder="field.placeholder ?? '0'"
          :required="field.required"
          :aria-invalid="error ? true : undefined"
          :class="['tabular-nums', field.bold && 'font-medium']"
          @keydown="onDecimalKey"
        />
        <NumberFieldIncrement />
      </NumberFieldContent>
    </NumberField>
    <span v-if="isBytes && hasValue" class="shrink-0 text-sm text-muted-foreground tabular-nums">
      {{ formatBytes(Number(modelValue)) }}
    </span>
  </div>
</template>
