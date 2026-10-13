<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useId } from 'vue'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Field, FieldDescription, FieldLabel } from '@/components/ui/field'

const { t } = useI18n()

const { field, updateField } = usePropertyEditor()
const id = useId()
</script>

<template>
  <Separator class="!mb-3" />
  <Field class="mb-4">
    <FieldLabel :for="`${id}-fetch-from`">{{ t('Fetch From') }}</FieldLabel>
    <Input
      :id="`${id}-fetch-from`"
      :model-value="field.fetch_from ?? ''"
      :placeholder="t('e.g. link_field.source_field')"
      @update:model-value="updateField('fetch_from', $event || undefined)"
    />
    <FieldDescription>
      {{ t('Fill the value automatically from another document when a Link field is chosen.') }}
      {{ t('Format:') }} <code class="bg-muted px-1 rounded">link_field.source_field</code>
    </FieldDescription>
  </Field>
</template>
