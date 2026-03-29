<script setup lang="ts">
import { defineAsyncComponent, computed } from 'vue'
import { fieldComponents, FallbackField } from '@/components/fields'
import { FormField } from '@/components/ui/form-field'
import { useDevMode } from '@/core/composables/useDevMode'
import type { DocField } from '@/types'

const { isDev, altPressed } = useDevMode()

const INLINE_LABEL_TYPES = new Set(['Check'])

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

const hasOwnLabel = computed(() => INLINE_LABEL_TYPES.has(props.field.fieldtype))
</script>

<template>
  <FormField
    v-if="isVisible"
    :data-fieldname="field.fieldname"
    :label="hasOwnLabel ? undefined : field.label"
    :required="hasOwnLabel ? false : field.required"
    :error="error"
    :hint="field.description"
    class="relative"
  >
    <component
      :is="component"
      :field="field"
      :modelValue="modelValue"
      :disabled="disabled"
      :error="error"
      @update:modelValue="emit('update:modelValue', $event)"
    />
    <span
      v-if="isDev && altPressed"
      class="absolute -top-2 right-1 z-50 rounded bg-violet-600 px-1.5 py-0.5 text-[10px] font-mono text-white shadow-sm pointer-events-none select-none"
    >{{ field.fieldname }}</span>
  </FormField>
</template>
