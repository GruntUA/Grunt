<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, useId } from 'vue'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Checkbox } from '@/components/ui/checkbox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Field, FieldGroup, FieldLabel, FieldLegend, FieldSet } from '@/components/ui/field'
import type { DocField } from '@/types'
import { isDateType } from '@/core/fieldRegistry'

const { field, updateField } = usePropertyEditor()
const { t } = useI18n()
const id = useId()

const FLAGS: { key: keyof DocField; label: string }[] = [
  { key: 'in_list_view', label: 'In List View' },
  { key: 'in_filter', label: 'In Filter' },
  { key: 'in_quick_filter', label: 'In Quick Filter' },
  { key: 'in_quick_entry', label: 'In Quick Entry' },
  { key: 'in_preview', label: 'In Preview' },
]

const isDateField = computed(() => isDateType(field.value.fieldtype))
</script>

<template>
  <Separator class="!mb-3" />
  <FieldSet class="mb-4">
    <FieldLegend variant="label">{{ t('Display') }}</FieldLegend>
    <FieldGroup class="gap-3">
      <template v-for="flag in FLAGS" :key="flag.key">
        <Field orientation="horizontal">
          <Checkbox :id="`${id}-${flag.key}`" :model-value="!!field[flag.key]" @update:model-value="updateField(flag.key, $event)" />
          <FieldLabel :for="`${id}-${flag.key}`" class="font-normal">{{ t(flag.label) }}</FieldLabel>
        </Field>
        <Field v-if="flag.key === 'in_quick_filter' && field.in_quick_filter && isDateField" class="pl-6">
          <FieldLabel :for="`${id}-quick-filter-mode`">{{ t('Quick Filter By') }}</FieldLabel>
          <Select :model-value="field.quick_filter_mode ?? 'date'" @update:model-value="updateField('quick_filter_mode', $event === 'year' ? 'year' : null)">
            <SelectTrigger :id="`${id}-quick-filter-mode`" class="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="date">{{ t('Date') }}</SelectItem>
              <SelectItem value="year">{{ t('Year') }}</SelectItem>
            </SelectContent>
          </Select>
        </Field>
      </template>
    </FieldGroup>
  </FieldSet>
</template>
