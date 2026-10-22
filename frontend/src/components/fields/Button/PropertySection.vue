<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import IconPicker from '@/components/fields/Icon/Icon.vue'
import { Separator } from '@/components/ui/separator'
import { Field, FieldGroup, FieldLabel, FieldLegend, FieldSet } from '@/components/ui/field'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'

const { field, updateField } = usePropertyEditor()
const { t } = useI18n()

const VARIANTS = [
  { value: 'default',     label: 'Primary' },
  { value: 'secondary',   label: 'Secondary' },
  { value: 'destructive', label: 'Destructive' },
  { value: 'outline',     label: 'Outline' },
  { value: 'ghost',       label: 'Ghost' },
]

const current = () => field.value.options ?? 'default'
</script>

<template>
  <Separator class="!mb-3" />
  <FieldSet class="mb-4">
    <FieldLegend variant="label">{{ t('Button') }}</FieldLegend>
    <FieldGroup class="gap-3">
      <Field>
        <FieldLabel>{{ t('Style') }}</FieldLabel>
        <ToggleGroup
          type="single" variant="outline" size="sm" class="flex-wrap"
          :model-value="current()"
          @update:model-value="(v) => v && updateField('options', v)"
        >
          <ToggleGroupItem v-for="v in VARIANTS" :key="v.value" :value="v.value">{{ t(v.label) }}</ToggleGroupItem>
        </ToggleGroup>
      </Field>
      <Field>
        <FieldLabel>{{ t('Icon') }}</FieldLabel>
        <IconPicker
          :field="field"
          :model-value="field.icon ?? null"
          @update:model-value="updateField('icon', $event ?? undefined)"
        />
      </Field>
    </FieldGroup>
  </FieldSet>
</template>
