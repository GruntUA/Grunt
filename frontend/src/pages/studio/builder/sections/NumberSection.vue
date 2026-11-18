<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, useId } from 'vue'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Field, FieldDescription, FieldLabel, FieldLegend, FieldSet } from '@/components/ui/field'

const { field, updateField } = usePropertyEditor()
const { t } = useI18n()
const id = useId()
// Decimal places - for the fractional types (Int has none).
const withPrecision = computed(() => ['Float', 'Currency', 'Percent'].includes(field.value.fieldtype))
</script>

<template>
  <Separator class="!mb-3" />
  <FieldSet class="mb-4">
    <FieldLegend variant="label">{{ t('Range') }}</FieldLegend>
    <div class="flex gap-2">
      <Field>
        <FieldLabel :for="`${id}-min`">{{ t('Min') }}</FieldLabel>
        <Input
          :id="`${id}-min`"
          type="number"
          :model-value="field.min_value ?? ''"
          @update:model-value="(v: string | number) => updateField('min_value', v === '' ? undefined : Number(v))"
        />
      </Field>
      <Field>
        <FieldLabel :for="`${id}-max`">{{ t('Max') }}</FieldLabel>
        <Input
          :id="`${id}-max`"
          type="number"
          :model-value="field.max_value ?? ''"
          @update:model-value="(v: string | number) => updateField('max_value', v === '' ? undefined : Number(v))"
        />
      </Field>
    </div>
    <Field v-if="withPrecision">
      <FieldLabel :for="`${id}-precision`">{{ t('Precision') }}</FieldLabel>
      <Input
        :id="`${id}-precision`"
        type="number"
        min="0"
        max="9"
        :placeholder="field.fieldtype === 'Currency' ? '2' : ''"
        :model-value="field.precision ?? ''"
        @update:model-value="(v: string | number) => updateField('precision', v === '' ? undefined : Number(v))"
      />
      <FieldDescription>{{ t('Decimal places: shown with and rounded to on save') }}</FieldDescription>
    </Field>
  </FieldSet>
</template>
