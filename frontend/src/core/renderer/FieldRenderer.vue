<script setup lang="ts">
import { defineAsyncComponent, computed } from 'vue'
import { fieldComponents, FallbackField } from '@/components/fields'
import type { DocField } from '@/types'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
  docValues?: Record<string, unknown>
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const isVisible = computed(() => {
  if (!props.field.depends_on) return true
  const expr = props.field.depends_on.replace(/^eval:\s*/, '')
  try {
    const doc = props.docValues ?? {}
    // eslint-disable-next-line no-new-func
    return !!(new Function('doc', `return !!(${expr})`))(doc)
  } catch {
    return true
  }
})

const component = computed(() =>
  defineAsyncComponent(fieldComponents[props.field.fieldtype] ?? FallbackField)
)
</script>

<template>
  <div v-if="isVisible">
    <component
      :is="component"
      :field="field"
      :modelValue="modelValue"
      :disabled="disabled"
      :error="error"
      @update:modelValue="emit('update:modelValue', $event)"
    />
  </div>
</template>
