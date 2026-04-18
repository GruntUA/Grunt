<script setup lang="ts">
import { computed } from 'vue'
import type { DocField } from '@/types'
import LinkField from '@/components/fields/Link/Link.vue'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
  doc?: Record<string, unknown>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: unknown]
  'create-new': [doctype: string, preset: string]
}>()

// field.options holds the fieldname of the field that contains the target doctype
const resolvedField = computed<DocField>(() => {
  const targetDoctype = props.doc && props.field.options
    ? String(props.doc[props.field.options] ?? '')
    : ''
  return { ...props.field, fieldtype: 'Link', options: targetDoctype }
})
</script>

<template>
  <LinkField
    :field="resolvedField"
    :model-value="modelValue"
    :disabled="disabled || !resolvedField.options"
    :error="error"
    :doc="doc"
    @update:model-value="emit('update:modelValue', $event)"
    @create-new="(doctype, preset) => emit('create-new', doctype, preset)"
  />
</template>
