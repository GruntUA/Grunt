<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useId } from 'vue'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Checkbox } from '@/components/ui/checkbox'
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldLegend, FieldSet } from '@/components/ui/field'
import { Badge } from '@/components/ui/badge'

const { t } = useI18n()

const { field, updateField } = usePropertyEditor()
const id = useId()
</script>

<template>
  <Separator class="!mb-3" />
  <FieldSet class="mb-4">
    <div class="flex items-center justify-between">
      <FieldLegend variant="label" class="mb-0">{{ t('Formula') }}</FieldLegend>
      <Badge v-if="field.formula" variant="secondary" class="font-mono">ƒx {{ t('is active') }}</Badge>
    </div>
    <FieldGroup class="gap-3">
      <Field>
        <FieldLabel :for="`${id}-formula`">{{ t('Expression (Python)') }}</FieldLabel>
        <Textarea
          :id="`${id}-formula`"
          :model-value="field.formula ?? ''"
          rows="2"
          placeholder="qty * unit_price"
          class="font-mono"
          @update:model-value="(v: string | number) => updateField('formula', String(v).trim() || null)"
        />
        <FieldDescription>
          {{ t('Computed on every save. All document fields are available as variables.') }}<br>
          {{ t('Examples:') }} <code class="bg-muted px-1 rounded">qty * price</code>,
          <code class="bg-muted px-1 rounded">round(a + b, 2)</code>,
          <code class="bg-muted px-1 rounded">first_name + ' ' + last_name</code>
        </FieldDescription>
      </Field>
      <Field v-if="field.formula" orientation="horizontal">
        <Checkbox :id="`${id}-read-only`" :model-value="!!field.read_only" @update:model-value="updateField('read_only', $event)" />
        <FieldLabel :for="`${id}-read-only`" class="font-normal">{{ t('Read Only (recommended)') }}</FieldLabel>
      </Field>
    </FieldGroup>
  </FieldSet>
</template>
