<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useId } from 'vue'
import { Input } from '@/components/ui/input'
import { Field, FieldLabel } from '@/components/ui/field'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'
import { isReportSourced } from './widgetHelpers'

const { t } = useI18n()
const id = useId()
const { widget, updateWidget } = useWidgetPropertyEditor()
</script>

<template>
  <Field v-if="!isReportSourced(widget)" class="mb-4">
    <FieldLabel :for="`${id}-1`">{{ t('Group by') }}</FieldLabel>
    <Input
      :id="`${id}-1`"
      :model-value="widget.group_by ?? ''"
      placeholder="fieldname"
      class="w-full"
      @update:model-value="updateWidget('group_by', $event)"
    />
  </Field>
</template>
