<script setup lang="ts">
import { computed } from 'vue'
import type { BaseFieldProps } from '@/types'
import { DatePicker } from '@/components/ui/date-picker'

const props = defineProps<BaseFieldProps>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const isDisabled = computed(() => !!(props.disabled || props.field.read_only))

const dateObj = computed<Date | null>({
  get() {
    const v = props.modelValue as string | null | undefined
    if (!v) return null
    try {
      const [y, m, d] = v.substring(0, 10).split('-').map(Number)
      const date = new Date(y, m - 1, d)
      return isNaN(date.getTime()) ? null : date
    } catch { return null }
  },
  set(val: Date | null) {
    if (!val) {
      emit('update:modelValue', null)
      return
    }
    const y = val.getFullYear()
    const m = String(val.getMonth() + 1).padStart(2, '0')
    const d = String(val.getDate()).padStart(2, '0')
    emit('update:modelValue', `${y}-${m}-${d}`)
  }
})

</script>

<template>
  <div class="w-full">
    <DatePicker
      v-model="dateObj"
      :disabled="isDisabled"
      :invalid="error"
      :placeholder="field.placeholder || 'ДД.ММ.РРРР'"
      class="w-full"
    />
  </div>
</template>
