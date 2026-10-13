<script setup lang="ts">
import { computed, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import { Input } from '@/components/ui/input'
import { Field, FieldLabel } from '@/components/ui/field'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'

const { t } = useI18n()
const id = useId()
const { widget, updateWidget } = useWidgetPropertyEditor()

const label = computed(() => widget.value.widget_type === 'clock' ? t('Note') : t('Subtitle'))
</script>

<template>
  <Field class="mb-4">
    <FieldLabel :for="`${id}-1`">{{ label }}</FieldLabel>
    <Input
      :id="`${id}-1`"
      :model-value="widget.description ?? ''"
      class="w-full"
      @update:model-value="updateWidget('description', $event)"
    />
  </Field>
</template>
