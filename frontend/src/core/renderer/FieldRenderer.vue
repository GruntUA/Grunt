<script setup lang="ts">
import { defineAsyncComponent, computed } from 'vue'
import { getFieldDef, FallbackFieldLoader } from '@/core/fieldRegistry'
import { useDevMode } from '@/core/composables/useDevMode'
import { validateFieldValue } from '@/core/validators'
import type { DocField } from '@/types'

const { isDev, altPressed } = useDevMode()

const INLINE_LABEL_TYPES = new Set(['Check', 'Button', 'Section', 'Column', 'Tab', 'Table'])

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
  'table-selection-change': [fieldname: string, rowNames: string[]]
}>()

const isVisible = computed(() => {
  if (props.field.hidden) return false
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

const validatorError = computed(() => {
  if (!props.field.validator) return null
  return validateFieldValue(props.field.validator, props.modelValue)
})

const displayError = computed(() => props.error || validatorError.value || null)

const component = computed(() =>
  defineAsyncComponent(getFieldDef(props.field.fieldtype)?.component ?? FallbackFieldLoader)
)

const hasOwnLabel = computed(() => INLINE_LABEL_TYPES.has(props.field.fieldtype))
</script>

<template>
  <div v-if="isVisible" :data-fieldname="field.fieldname"
    class="flex flex-col gap-1.5 relative w-full p-1.5 -m-1.5 rounded-lg transition-colors"
    :class="{
      'bg-destructive/[0.03] ring-1 ring-destructive/20': displayError,
      'hover:bg-muted/30': !displayError
    }">
    <label v-if="!hasOwnLabel" class="text-sm font-medium text-foreground/90 flex items-center gap-1">
      {{ field.label }}
      <span v-if="field.required" class="text-destructive font-semibold">*</span>
    </label>

    <component
      :is="component"
      :field="field"
      :modelValue="modelValue"
      :disabled="disabled"
      :error="displayError"
      :doc="docValues"
      @update:modelValue="emit('update:modelValue', $event)"
      @create-new="(doctype: string, preset: string) => emit('create-new', doctype, preset, field.fieldname)"
      @selection-change="(rowNames: string[]) => emit('table-selection-change', field.fieldname, rowNames)"
    />

    <p v-if="field.description" class="text-xs text-muted-foreground leading-snug">
      {{ field.description }}
    </p>

    <p v-if="displayError" class="text-xs text-destructive font-medium animate-in fade-in slide-in-from-top-1 duration-200">
      {{ displayError }}
    </p>

    <span v-if="isDev && altPressed"
      class="absolute -top-2 right-1 z-50 rounded bg-foreground px-1.5 py-0.5 text-xs font-mono text-background pointer-events-none select-none">
      {{ field.fieldname }}
    </span>
  </div>
</template>
