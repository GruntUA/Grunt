<script setup lang="ts">
import type { BaseFieldProps } from '@/types'
import { Textarea } from '@/components/ui/textarea'

const props = defineProps<BaseFieldProps>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

function onUpdate(v: string | number) {
  emit('update:modelValue', String(v ?? ''))
}
</script>

<template>
  <Textarea
    :model-value="String(props.modelValue ?? '')"
    :placeholder="field.placeholder ?? ''"
    :disabled="disabled || field.read_only"
    :required="field.required"
    :maxlength="field.max_length || undefined"
    :aria-invalid="error ? true : undefined"
    :aria-label="field.label"
    rows="3"
    class="max-h-64 w-full overflow-y-auto"
    @update:model-value="onUpdate"
  />
</template>
