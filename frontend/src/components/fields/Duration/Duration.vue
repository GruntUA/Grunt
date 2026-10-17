<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import type { DocField } from '@/types'
import { Input } from '@/components/ui/input'
import {
  NumberField, NumberFieldContent, NumberFieldDecrement, NumberFieldIncrement, NumberFieldInput,
} from '@/components/ui/number-field'
import { durationUnit, formatDuration, splitDuration } from '@/core/duration'
import { localeTag } from '@/core/composables/useNumberField'

const { t } = useI18n()

const props = defineProps<{
  field: DocField
  modelValue: number | null | undefined
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: number | null] }>()

const unit = computed(() => durationUnit(props.field))
const readable = computed(() => formatDuration(props.modelValue, unit.value))
// Nothing to type when locked - show just the readable value, raw on hover.
const locked = computed(() => props.disabled || props.field.read_only)

const total = computed(() => {
  const n = Number(props.modelValue)
  return props.modelValue == null || !Number.isFinite(n) ? 0 : n
})
const segments = computed(() => splitDuration(total.value, unit.value))

/**
 * A segment edit shifts the total by the difference, so the value carries
 * and borrows across units: `−` on `1 h 0 min` gives `59 min`, typing `90`
 * minutes gives `1 h 30 min` once the segments re-derive from the total.
 */
function onSegment(index: number, value: number | null | undefined) {
  const seg = segments.value[index]
  if (!seg) return
  const next = Number.isFinite(value) ? Math.trunc(value as number) : 0
  let result = total.value + (next - seg.count) * seg.size
  result = Math.max(0, result)
  if (props.field.max_value != null) result = Math.min(result, props.field.max_value)
  emit('update:modelValue', result)
}

const formatOptions: Intl.NumberFormatOptions = { maximumFractionDigits: 0, useGrouping: false }
</script>

<template>
  <Input
    v-if="locked"
    disabled
    :model-value="readable"
    :title="modelValue != null ? String(modelValue) : undefined"
    :placeholder="field.placeholder ?? ''"
    :class="['w-full tabular-nums', field.bold && 'font-medium']"
  />
  <div
    v-else
    role="group"
    :aria-label="field.label"
    :aria-invalid="error ? true : undefined"
    :class="['grid gap-2', segments.length > 4 ? 'grid-cols-3 sm:grid-cols-5' : 'grid-cols-2 sm:grid-cols-4']"
  >
    <!-- An empty value shows zeros: from null, reka's `+` jumps to `min`, not 1.
         Below one unit there is nothing to borrow from - `−` stops at zero. -->
    <NumberField
      v-for="(seg, i) in segments"
      :key="seg.key"
      :model-value="seg.count"
      :locale="localeTag()"
      :format-options="formatOptions"
      :step-snapping="false"
      :min="total < seg.size ? 0 : undefined"
      disable-wheel-change
      class="gap-1"
      @update:model-value="onSegment(i, $event)"
    >
      <NumberFieldContent>
        <NumberFieldDecrement />
        <NumberFieldInput
          placeholder="0"
          :aria-label="t(seg.label)"
          :class="['tabular-nums', field.bold && 'font-medium']"
        />
        <NumberFieldIncrement />
      </NumberFieldContent>
      <span class="text-center text-xs text-muted-foreground">{{ t(seg.label) }}</span>
    </NumberField>
  </div>
</template>
