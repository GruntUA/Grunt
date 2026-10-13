<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useId } from 'vue'
import { Input } from '@/components/ui/input'
import { Field, FieldLabel } from '@/components/ui/field'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'

const { t } = useI18n()
const id = useId()
const { widget, updateWidget } = useWidgetPropertyEditor()
</script>

<template>
  <Field class="mb-4">
    <FieldLabel :for="`${id}-1`">{{ t('Title') }}</FieldLabel>
    <Input
      :id="`${id}-1`"
      :model-value="widget.title"
      :placeholder="t('Widget title')"
      class="w-full"
      @update:model-value="updateWidget('title', $event)"
    />
  </Field>
</template>
