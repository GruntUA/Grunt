<script setup lang="ts">
import { computed } from 'vue'
import type { DocField } from '@/types'
import MultiSelect from 'primevue/multiselect'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const parsedOptions = computed(() =>
  typeof props.field.options === 'string'
    ? props.field.options.split('\n').map(o => o.trim()).filter(Boolean)
    : []
)

const selectedValues = computed<string[]>(() => {
  const v = props.modelValue
  if (Array.isArray(v)) return v as string[]
  if (typeof v === 'string' && v) {
    try { return JSON.parse(v) as string[] } catch { return [] }
  }
  return []
})
</script>

<template>
  <MultiSelect
    :model-value="selectedValues"
    :options="parsedOptions"
    display="chip"
    filter
    :disabled="disabled || field.read_only"
    :invalid="!!error"
    placeholder="— оберіть —"
    class="w-full"
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>
