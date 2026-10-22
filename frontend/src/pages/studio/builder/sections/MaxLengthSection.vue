<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useId } from 'vue'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Field, FieldLabel } from '@/components/ui/field'

const { field, updateField } = usePropertyEditor()
const id = useId()
const { t } = useI18n()
</script>

<template>
  <Separator class="!mb-3" />
  <Field class="mb-4">
    <FieldLabel :for="`${id}-max-length`">{{ t('Max Length') }}</FieldLabel>
    <Input
      :id="`${id}-max-length`"
      type="number"
      :model-value="field.max_length ?? ''"
      placeholder="255"
      @update:model-value="(v: string | number) => updateField('max_length', v === '' ? undefined : Number(v))"
    />
  </Field>
</template>
