<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useId } from 'vue'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Checkbox } from '@/components/ui/checkbox'
import { Separator } from '@/components/ui/separator'
import { Field, FieldGroup, FieldLabel, FieldLegend, FieldSet } from '@/components/ui/field'
import type { DocField } from '@/types'

const { field, updateField } = usePropertyEditor()
const { t } = useI18n()
const id = useId()

const FLAGS: { key: keyof DocField; label: string }[] = [
  { key: 'required', label: 'Required' },
  { key: 'hidden', label: 'Hidden' },
  { key: 'read_only', label: 'Read Only' },
  { key: 'bold', label: 'Bold' },
  { key: 'unique', label: 'Unique' },
  { key: 'index', label: 'Index' },
]
</script>

<template>
  <Separator class="!mb-3" />
  <FieldSet class="mb-4">
    <FieldLegend variant="label">{{ t('Flags') }}</FieldLegend>
    <FieldGroup class="gap-3">
      <Field v-for="flag in FLAGS" :key="flag.key" orientation="horizontal" :data-disabled="flag.key === 'index' && !!field.unique">
        <Checkbox
          :id="`${id}-${flag.key}`"
          :model-value="!!field[flag.key]"
          :disabled="flag.key === 'index' && !!field.unique"
          @update:model-value="updateField(flag.key, $event)"
        />
        <FieldLabel :for="`${id}-${flag.key}`" class="font-normal">{{ t(flag.label) }}</FieldLabel>
      </Field>
    </FieldGroup>
  </FieldSet>
</template>
