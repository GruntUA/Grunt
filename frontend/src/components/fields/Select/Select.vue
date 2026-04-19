<script setup lang="ts">
import { computed } from 'vue'
import Select from 'primevue/select'
import type { DocField } from '@/types'

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
    : (props.field.options ?? [])
)
</script>

<template>
  <Select
    :model-value="String(modelValue ?? '')"
    :options="parsedOptions"
    :disabled="disabled || field.read_only"
    placeholder="— оберіть —"
    class="w-full"
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>
