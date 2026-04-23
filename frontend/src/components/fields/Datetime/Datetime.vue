<script setup lang="ts">
import { computed } from 'vue'
import type { DocField } from '@/types'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: boolean
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

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
  }
})

</script>

<template>
  <div class="w-full">
    <DatePicker
      v-model="dateObj"
      :disabled="isDisabled"
      :invalid="error"
      show-time
      hour-format="24"
      date-format="dd.mm.yy"
      :placeholder="field.placeholder || 'ДД.ММ.РРРР ГГ:ХХ'"
      show-icon
      icon-display="input"
      class="w-full"
      fluid
    />
  </div>
</template>
