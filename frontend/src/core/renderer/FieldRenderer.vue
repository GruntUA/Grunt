<script setup lang="ts">
import { computed, inject, useId } from 'vue'
import { getAsyncFieldComponent } from '@/core/fieldRegistry'
import { useDevMode } from '@/core/composables/useDevMode'
import { validateFieldValue } from '@/core/validators'
import { evalDependsOn } from '@/core/dependsOn'
import { FORM_ERRORS } from './formErrors'
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
  return evalDependsOn(props.field.depends_on, props.docValues ?? {})
})

const validatorError = computed(() => {
  if (!props.field.validator) return null
  return validateFieldValue(props.field.validator, props.modelValue)
})

// Fallback to the form-wide error map (used for nested sub-form fields, which
// aren't passed an explicit `error` prop by their container).
const formErrors = inject(FORM_ERRORS, null)
const injectedError = computed(() =>
  formErrors ? formErrors.errors.value[formErrors.prefix + props.field.fieldname] : undefined,
)

const displayError = computed(() => props.error || injectedError.value || validatorError.value || null)

const component = computed(() => getAsyncFieldComponent(props.field.fieldtype))

const hasOwnLabel = computed(() => INLINE_LABEL_TYPES.has(props.field.fieldtype))

// A11y wiring: the label / description / error <p>s are separate siblings of
// the control, so tie them together. Fields render many different root
// elements (and several aren't a single input), so name the whole field as an
// ARIA group rather than trying to put `for`/`id` on each control.
const uid = useId()
const labelId = `${uid}-label`
const descId = `${uid}-desc`
const errId = `${uid}-err`

const describedBy = computed(() => {
  const ids: string[] = []
  if (props.field.description) ids.push(descId)
  if (displayError.value) ids.push(errId)
  return ids.length ? ids.join(' ') : undefined
})
</script>

<template>
  <div v-if="isVisible" :data-fieldname="field.fieldname"
    :role="!hasOwnLabel ? 'group' : undefined"
    :aria-labelledby="!hasOwnLabel ? labelId : undefined"
    :aria-describedby="describedBy"
    class="flex flex-col gap-1.5 relative w-full p-1.5 -m-1.5 rounded-lg transition-colors"
    :class="{
      'bg-destructive/[0.03] ring-1 ring-destructive/20': displayError,
      'hover:bg-muted/30': !displayError
    }">
    <label v-if="!hasOwnLabel" :id="labelId" class="font-medium text-foreground/90 flex items-center gap-1">
      {{ field.label }}
      <span v-if="field.required" class="text-destructive font-semibold" aria-hidden="true">*</span>
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

    <p v-if="field.description" :id="descId" class="text-xs text-muted-foreground leading-snug whitespace-pre-line">
      {{ field.description }}
    </p>

    <p v-if="displayError" :id="errId" aria-live="polite" aria-atomic="true"
      class="text-xs text-destructive font-medium animate-in fade-in slide-in-from-top-1 duration-200">
      {{ displayError }}
    </p>

    <span v-if="isDev && altPressed"
      class="absolute -top-2 right-1 z-50 rounded bg-foreground px-1.5 py-0.5 text-xs font-mono text-background pointer-events-none select-none">
      {{ field.fieldname }}
    </span>
  </div>
</template>
