<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Separator } from '@/components/ui/separator'
import Code from '@/components/fields/Code/Code.vue'
import { FieldLegend, FieldSet } from '@/components/ui/field'

const { field, updateField } = usePropertyEditor()
const { t } = useI18n()
</script>

<template>
  <Separator class="!mb-3" />
  <FieldSet class="mb-4">
    <FieldLegend variant="label">{{ t('Options') }}</FieldLegend>
    <Code
      :field="{ ...field, options: 'html' }"
      :model-value="field.options ?? ''"
      @update:model-value="(v: string) => updateField('options', v)"
    />
  </FieldSet>
</template>
