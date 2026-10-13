<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useId } from 'vue'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Field, FieldGroup, FieldLabel, FieldLegend, FieldSet } from '@/components/ui/field'

const { field, updateField } = usePropertyEditor()
const { t } = useI18n()
const id = useId()
</script>

<template>
  <Separator class="!mb-3" />
  <FieldSet class="mb-4">
    <FieldLegend variant="label">{{ t('Text') }}</FieldLegend>
    <FieldGroup class="gap-3">
      <Field>
        <FieldLabel :for="`${id}-description`">{{ t('Description') }}</FieldLabel>
        <Input :id="`${id}-description`" :model-value="field.description ?? ''" @update:model-value="updateField('description', $event || undefined)" />
      </Field>
      <Field>
        <FieldLabel :for="`${id}-placeholder`">{{ t('Placeholder') }}</FieldLabel>
        <Input :id="`${id}-placeholder`" :model-value="field.placeholder ?? ''" @update:model-value="updateField('placeholder', $event || undefined)" />
      </Field>
      <Field>
        <FieldLabel :for="`${id}-depends-on`">{{ t('Depends On') }}</FieldLabel>
        <Input :id="`${id}-depends-on`" :model-value="field.depends_on ?? ''" placeholder="eval: doc.status == 'Active'" @update:model-value="updateField('depends_on', $event || undefined)" />
      </Field>
      <Field>
        <FieldLabel :for="`${id}-mandatory-depends-on`">{{ t('Mandatory Depends On') }}</FieldLabel>
        <Input :id="`${id}-mandatory-depends-on`" :model-value="field.mandatory_depends_on ?? ''" placeholder="eval: doc.type == 'Full'" @update:model-value="updateField('mandatory_depends_on', $event || undefined)" />
      </Field>
    </FieldGroup>
  </FieldSet>
</template>
