<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useId } from 'vue'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'
import HTMLEditor from '@/components/fields/HTMLEditor/HTMLEditor.vue'
import { Field, FieldContent, FieldDescription, FieldGroup, FieldLabel, FieldLegend, FieldSet } from '@/components/ui/field'

const { field, updateField } = usePropertyEditor()
const id = useId()
const { t } = useI18n()
</script>

<template>
  <Separator class="!mb-3" />
  <FieldSet class="mb-4">
    <FieldLegend variant="label">{{ t('Options') }}</FieldLegend>
    <Field v-if="field.fieldtype === 'Currency'">
      <Input
        :model-value="field.options ?? ''"
        :placeholder="t('currency or UAH')"
        :aria-label="t('Options')"
        @update:model-value="(v: string | number) => updateField('options', String(v))"
      />
      <FieldDescription>{{ t('A Link field to Currency in this document, or a fixed ISO currency code') }}</FieldDescription>
    </Field>
    <Field v-else-if="field.fieldtype === 'Duration'">
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
    <HTMLEditor
      v-else-if="field.fieldtype === 'HTML'"
      :field="field"
      :model-value="field.options ?? ''"
      @update:model-value="(v: string) => updateField('options', v)"
    />
    <FieldGroup v-else class="gap-3">
      <Textarea
        :model-value="field.options ?? ''"
        rows="5"
        :placeholder="field.fieldtype === 'Data' ? t('Autocomplete suggestions — one per line') : t('One option per line')"
        :aria-label="t('Options')"
        @update:model-value="(v: string | number) => updateField('options', String(v))"
      />
      <Field v-if="field.fieldtype === 'Select' || field.fieldtype === 'MultiSelect'" orientation="horizontal">
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
