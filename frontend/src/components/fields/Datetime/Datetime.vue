<script setup lang="ts">
import { computed } from 'vue'
import type { BaseFieldProps } from '@/types'
import { DatePicker } from '@/components/ui/date-picker'

const props = defineProps<BaseFieldProps>()

const emit = defineEmits<{
  'update:modelValue': [value: unknown]
}>()

const isDisabled = computed(() => !!(props.disabled || props.field.read_only))

const dateObj = computed<Date | null>({
  get() {
    const v = props.modelValue as string | null | undefined
    if (!v) return null
    try {
      const d = new Date(v.replace(' ', 'T'))
      return isNaN(d.getTime()) ? null : d
    } catch { return null }
  },
  set(val: Date | null) {
    if (!val) {
      emit('update:modelValue', null)
      return
    }
    // Datetimes are stored as UTC (grunt/db/types.py treats a naive value as
    // UTC), so send an explicit instant — a naive local wall-clock string
    // would come back shifted by the viewer's UTC offset.
    emit('update:modelValue', val.toISOString())
  },
})
</script>

<template>
  <DatePicker
    v-model="dateObj"
    show-time
    :disabled="isDisabled"
    :invalid="!!error"
    :placeholder="field.placeholder || undefined"
    class="w-full"
  />
</template>
