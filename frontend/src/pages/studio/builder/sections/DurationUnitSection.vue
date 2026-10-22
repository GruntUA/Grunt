<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
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
      <Select
        :model-value="field.options?.trim() === 'ms' ? 'ms' : 's'"
        @update:model-value="(v) => updateField('options', v === 'ms' ? 'ms' : '')"
      >
        <SelectTrigger class="w-full" :aria-label="t('Unit')"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value="s">{{ t('Seconds') }}</SelectItem>
          <SelectItem value="ms">{{ t('Milliseconds') }}</SelectItem>
        </SelectContent>
      </Select>
      <FieldDescription>{{ t('Unit of the stored number') }}</FieldDescription>
    </Field>
  </FieldSet>
</template>
