<script setup lang="ts">
import { computed } from 'vue'
import type { DocField } from '@/types'
import LinkField from '@/components/fields/Link/Link.vue'
import DataField from '@/components/fields/Data/Data.vue'

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

// field.options holds the fieldname whose value is the target doctype name.
// Empty string → no doctype resolved → fall back to plain text input.
const targetDoctype = computed(() =>
  props.doc && props.field.options
    ? String(props.doc[props.field.options] ?? '')
    : ''
)

const isLinkMode = computed(() => !!targetDoctype.value)

const resolvedLinkField = computed<DocField>(() => ({
  ...props.field,
  fieldtype: 'Link',
  options: targetDoctype.value,
}))
</script>

<template>
  <LinkField
    v-if="isLinkMode"
    :field="resolvedLinkField"
    :model-value="modelValue"
    :disabled="disabled"
    :error="error"
    :doc="doc"
    @update:model-value="emit('update:modelValue', $event)"
    @create-new="(doctype, preset) => emit('create-new', doctype, preset)"
  />
  <DataField
    v-else
    :field="field"
    :model-value="modelValue"
    :disabled="disabled"
    :error="error"
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>
