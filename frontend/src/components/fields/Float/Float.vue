<script setup lang="ts">
import type { DocField } from '@/types'
import { Input } from '@/components/ui/input'

defineProps<{
  field: DocField
  modelValue: number | null | undefined
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: number | null] }>()
</script>

<template>
  <Input
    type="number"
    step="any"
    :model-value="modelValue ?? ''"
    :placeholder="field.placeholder ?? '0.0'"
    :required="field.required"
    :disabled="disabled || field.read_only"
    class="w-full"
    @update:model-value="(v: string | number) => emit('update:modelValue', v === '' ? null : Number(v))"
  />
</template>
