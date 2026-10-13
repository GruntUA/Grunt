<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useId } from 'vue'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Checkbox } from '@/components/ui/checkbox'
import { Field, FieldLabel } from '@/components/ui/field'

const { field, updateField } = usePropertyEditor()
const { t } = useI18n()
const id = useId()
</script>

<template>
  <Field orientation="horizontal" class="mb-4">
    <Checkbox :id="`${id}-collapsible`" :model-value="!!field.collapsible" @update:model-value="updateField('collapsible', $event)" />
    <FieldLabel :for="`${id}-collapsible`" class="font-normal">{{ t('Collapsible') }}</FieldLabel>
  </Field>
</template>
