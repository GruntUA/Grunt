<script setup lang="ts">
import type { BaseFieldProps } from '@/types'
import { Input } from '@/components/ui/input'

defineProps<BaseFieldProps>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()
</script>

<template>
  <Input
    :model-value="String(modelValue ?? '')"
    :placeholder="field.placeholder ?? field.label"
    :required="field.required"
    :disabled="disabled || field.read_only"
    class="w-full"
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>
