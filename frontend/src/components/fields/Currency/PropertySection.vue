<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Field, FieldDescription, FieldLegend, FieldSet } from '@/components/ui/field'

const { field, updateField } = usePropertyEditor()
const { t } = useI18n()
</script>

<template>
  <Separator class="!mb-3" />
  <FieldSet class="mb-4">
    <FieldLegend variant="label">{{ t('Options') }}</FieldLegend>
    <Field>
      <Input
        :model-value="field.options ?? ''"
        :placeholder="t('currency or UAH')"
        :aria-label="t('Options')"
        @update:model-value="(v: string | number) => updateField('options', String(v))"
      />
      <FieldDescription>{{ t('A Link field to Currency in this document, or a fixed ISO currency code') }}</FieldDescription>
    </Field>
  </FieldSet>
</template>
