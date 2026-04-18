<script setup lang="ts">
import { defineAsyncComponent, computed } from 'vue'
import { getFieldDef, FallbackFieldLoader } from '@/core/fieldRegistry'
import { Field, FieldLabel, FieldDescription, FieldError } from '@/components/ui/field'
import { useDevMode } from '@/core/composables/useDevMode'
import type { DocField } from '@/types'

const { isDev, altPressed } = useDevMode()

const INLINE_LABEL_TYPES = new Set(['Check', 'Button'])

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
  docValues?: Record<string, unknown>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: unknown]
  'create-new': [doctype: string, preset: string, fieldname: string]
}>()

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
  defineAsyncComponent(getFieldDef(props.field.fieldtype)?.component ?? FallbackFieldLoader)
)

const hasOwnLabel = computed(() => INLINE_LABEL_TYPES.has(props.field.fieldtype))
</script>

<template>
  <Field v-if="isVisible" :data-fieldname="field.fieldname" class="relative">
    <FieldLabel v-if="!hasOwnLabel">
      {{ field.label }}
      <span v-if="field.required" class="text-destructive ml-0.5">*</span>
    </FieldLabel>
    <component :is="component" :field="field" :modelValue="modelValue" :disabled="disabled" :error="error"
      :doc="docValues" @update:modelValue="emit('update:modelValue', $event)"
      @create-new="(doctype: string, preset: string) => emit('create-new', doctype, preset, field.fieldname)" />
    <FieldDescription v-if="field.description">{{ field.description }}</FieldDescription>
    <FieldError v-if="error">{{ error }}</FieldError>
    <span v-if="isDev && altPressed"
      class="absolute -top-2 right-1 z-50 rounded bg-violet-600 px-1.5 py-0.5 text-[10px] font-mono text-white shadow-sm pointer-events-none select-none">{{
        field.fieldname }}</span>
  </Field>
</template>
