<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, useId } from 'vue'
import { useBuilderStore } from '@/stores/builder'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldLegend, FieldSet } from '@/components/ui/field'
import { Badge } from '@/components/ui/badge'
import { hasTrait } from '@/core/fieldRegistry'

const { t } = useI18n()

const { field, updateField } = usePropertyEditor()
const id = useId()
const builder = useBuilderStore()

const AGGREGATE_FUNCTIONS = [
  { value: '__none__', label: t('— no aggregation —') },
  { value: 'sum', label: t('sum — total') },
  { value: 'count', label: t('count — number of rows') },
  { value: 'avg', label: t('avg — average') },
  { value: 'min', label: t('min — minimum') },
  { value: 'max', label: t('max — maximum') },
]

const tableFields = computed(() =>
  (builder.doctype?.fields ?? []).filter((f) => hasTrait(f.fieldtype, 'table')).map(f => ({
    value: f.fieldname,
    label: `${f.label || f.fieldname} (${f.fieldname})`,
  }))
)
</script>

<template>
  <Separator class="!mb-3" />
  <FieldSet class="mb-4">
    <div class="flex items-center justify-between">
      <FieldLegend variant="label" class="mb-0">{{ t('Aggregation') }}</FieldLegend>
      <Badge v-if="field.aggregate_function" variant="secondary" class="font-mono">∑ {{ t('is active') }}</Badge>
    </div>
    <FieldGroup class="gap-3">
      <Field>
        <FieldLabel :for="`${id}-function`">{{ t('Function') }}</FieldLabel>
        <Select :model-value="field.aggregate_function ?? '__none__'" @update:model-value="updateField('aggregate_function', $event === '__none__' ? null : $event)">
          <SelectTrigger :id="`${id}-function`" class="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in AGGREGATE_FUNCTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
          </SelectContent>
        </Select>
      </Field>
      <template v-if="field.aggregate_function">
        <Field>
          <FieldLabel :for="`${id}-table`">{{ t('Table (TABLE field)') }}</FieldLabel>
          <Select :model-value="field.aggregate_table ?? ''" :empty-message="t('No TABLE fields in this DocType')" @update:model-value="updateField('aggregate_table', $event || null)">
            <SelectTrigger :id="`${id}-table`" class="w-full">
              <SelectValue :placeholder="t('— choose a TABLE field —')" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="opt in tableFields" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <Field v-if="field.aggregate_function !== 'count'">
          <FieldLabel :for="`${id}-field`">{{ t('Child DocType field') }}</FieldLabel>
          <Input
            :id="`${id}-field`"
            :model-value="field.aggregate_field ?? ''"
            :placeholder="t('e.g. amount')"
            @update:model-value="updateField('aggregate_field', $event || null)"
          />
          <FieldDescription>{{ t('Fieldname of a numeric field in the child DocType') }}</FieldDescription>
        </Field>
      </template>
    </FieldGroup>
  </FieldSet>
</template>
