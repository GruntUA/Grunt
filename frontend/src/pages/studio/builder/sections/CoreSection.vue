<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useId } from 'vue'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { getLayoutTypeSet } from '@/core/fieldRegistry'
import { Input } from '@/components/ui/input'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'

const { field, updateField } = usePropertyEditor()
const { t } = useI18n()
const id = useId()
const LAYOUT_TYPES = getLayoutTypeSet()
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
  </FieldGroup>
</template>
