<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, useId } from 'vue'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { getLayoutTypeSet } from '@/core/fieldRegistry'
import { Input } from '@/components/ui/input'
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { twelfths } from '@/core/renderer/formGrid'

const { field, updateField } = usePropertyEditor()
const { t } = useI18n()
const id = useId()
const LAYOUT_TYPES = getLayoutTypeSet()

// `columns`: width in twelfths - of the section for a Column, of the column for a field.
const NO_WIDTH = new Set(['Tab', 'Section'])
const WIDTHS: { value: number; label: string }[] = [
  { value: 12, label: 'Full width' },
  { value: 9, label: '3/4' },
  { value: 8, label: '2/3' },
  { value: 6, label: '1/2' },
  { value: 4, label: '1/3' },
  { value: 3, label: '1/4' },
  { value: 2, label: '1/6' },
]
const width = computed(() => String(twelfths(field.value.columns)))
const widthOptions = computed(() =>
  WIDTHS.some((w) => String(w.value) === width.value)
    ? WIDTHS
    : [...WIDTHS, { value: Number(width.value), label: `${width.value}/12` }],
)
</script>

<template>
  <FieldGroup class="mb-4 gap-3">
    <Field>
      <FieldLabel :for="`${id}-label`">{{ t('Label') }}</FieldLabel>
      <Input :id="`${id}-label`" :model-value="field.label" @update:model-value="updateField('label', $event)" />
    </Field>
    <Field :data-disabled="LAYOUT_TYPES.has(field.fieldtype)">
      <FieldLabel :for="`${id}-fieldname`">{{ t('Fieldname') }}</FieldLabel>
      <Input
        :id="`${id}-fieldname`"
        :model-value="field.fieldname"
        :disabled="LAYOUT_TYPES.has(field.fieldtype)"
        @update:model-value="updateField('fieldname', $event)"
      />
    </Field>
    <Field v-if="!NO_WIDTH.has(field.fieldtype)">
      <FieldLabel :for="`${id}-width`">{{ t('Width') }}</FieldLabel>
      <Select :model-value="width" @update:model-value="updateField('columns', Number($event))">
        <SelectTrigger :id="`${id}-width`" class="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem v-for="w in widthOptions" :key="w.value" :value="String(w.value)">
            {{ w.value === 12 ? t(w.label) : w.label }}
          </SelectItem>
        </SelectContent>
      </Select>
      <FieldDescription>
        {{ field.fieldtype === 'Column' ? t('Share of the section; columns without a width split the rest') : t('Share of its column; narrow fields stand side by side') }}
      </FieldDescription>
    </Field>
  </FieldGroup>
</template>
