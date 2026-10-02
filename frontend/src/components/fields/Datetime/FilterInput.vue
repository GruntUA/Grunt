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

// The filter value keeps the YYYY-MM-DDTHH:mm wall-clock form the filter has always sent.
const date = computed<Date | null>({
  get() {
    if (!props.modelValue) return null
    const d = new Date(props.modelValue)
    return isNaN(d.getTime()) ? null : d
  },
  set(v) {
    emit('update:modelValue', v
      ? `${v.getFullYear()}-${pad(v.getMonth() + 1)}-${pad(v.getDate())}T${pad(v.getHours())}:${pad(v.getMinutes())}`
      : '')
  },
})
</script>

<template>
  <DatePicker v-model="date" show-time class="w-full" />
</template>
