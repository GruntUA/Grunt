<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useId } from 'vue'
import { Textarea } from '@/components/ui/textarea'
import { Field, FieldLabel } from '@/components/ui/field'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'

const { t } = useI18n()
const id = useId()
const { widget, updateWidget } = useWidgetPropertyEditor()
</script>

<template>
  <Field class="mb-4">
    <FieldLabel :for="`${id}-1`">{{ t('Content (HTML/text)') }}</FieldLabel>
    <Textarea
      :id="`${id}-1`"
      :model-value="widget.content ?? ''"
      rows="5"
      class="w-full !font-mono !text-sm"
      @update:model-value="(v: string | number) => updateWidget('content', String(v))"
    />
  </Field>
</template>
