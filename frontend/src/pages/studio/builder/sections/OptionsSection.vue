<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useId } from 'vue'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Checkbox } from '@/components/ui/checkbox'
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'
import { hasTrait } from '@/core/fieldRegistry'
import { Field, FieldContent, FieldDescription, FieldGroup, FieldLabel, FieldLegend, FieldSet } from '@/components/ui/field'

const { field, updateField } = usePropertyEditor()
const id = useId()
const { t } = useI18n()
</script>

<template>
  <Separator class="!mb-3" />
  <FieldSet class="mb-4">
    <FieldLegend variant="label">{{ t('Options') }}</FieldLegend>
    <FieldGroup class="gap-3">
      <Textarea
        :model-value="field.options ?? ''"
        rows="5"
        :placeholder="field.fieldtype === 'Data' ? t('Autocomplete suggestions — one per line') : t('One option per line')"
        :aria-label="t('Options')"
        @update:model-value="(v: string | number) => updateField('options', String(v))"
      />
      <Field v-if="hasTrait(field.fieldtype, 'options')" orientation="horizontal">
        <Checkbox
          :id="`${id}-translatable`"
          :model-value="!!field.translatable"
          @update:model-value="updateField('translatable', $event)"
        />
        <FieldContent>
          <FieldLabel :for="`${id}-translatable`" class="font-normal">{{ t('Translatable') }}</FieldLabel>
          <FieldDescription>{{ t('Option captions are translated; stored values stay unchanged.') }}</FieldDescription>
        </FieldContent>
      </Field>
    </FieldGroup>
  </FieldSet>
</template>
