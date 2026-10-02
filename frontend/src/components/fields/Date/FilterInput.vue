<script setup lang="ts">
import { computed } from 'vue'
import type { DocField } from '@/types'
import { DatePicker } from '@/components/ui/date-picker'

const props = defineProps<{
  field: DocField
  modelValue: string
  displayValue: string
  op: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:displayValue': [value: string]
  'submit': []
}>()

const pad = (n: number) => String(n).padStart(2, '0')

// The filter value is a plain YYYY-MM-DD date.
const date = computed<Date | null>({
  get() {
    const [y, m, d] = props.modelValue.split('-').map(Number)
    return y && m && d ? new Date(y, m - 1, d) : null
  },
  set(v) {
    emit('update:modelValue', v ? `${v.getFullYear()}-${pad(v.getMonth() + 1)}-${pad(v.getDate())}` : '')
  },
})
</script>

<template>
  <DatePicker v-model="date" class="w-full" />
</template>
