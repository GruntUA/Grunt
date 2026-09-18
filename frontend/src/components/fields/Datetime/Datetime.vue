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
    const y = val.getFullYear()
    const mo = String(val.getMonth() + 1).padStart(2, '0')
    const day = String(val.getDate()).padStart(2, '0')
    const h = String(val.getHours()).padStart(2, '0')
    const mi = String(val.getMinutes()).padStart(2, '0')
    const s = String(val.getSeconds()).padStart(2, '0')
    emit('update:modelValue', `${y}-${mo}-${day} ${h}:${mi}:${s}`)
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
