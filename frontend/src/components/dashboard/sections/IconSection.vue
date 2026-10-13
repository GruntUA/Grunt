<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DocField } from '@/types'
import IconPicker from '@/components/fields/Icon/Icon.vue'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'

const { t } = useI18n()
const { widget, updateWidget } = useWidgetPropertyEditor()

// IconPicker is a DocField-input component - this stub only needs the two
// properties it actually reads (label, read_only).
const iconField = computed<DocField>(() => ({
  fieldname: 'icon',
  label: t('Icon (lucide)'),
  fieldtype: 'Icon',
}))
</script>

<template>
  <Field class="mb-4">
    <FieldLabel>{{ t('Icon (lucide)') }}</FieldLabel>
    <IconPicker
      :field="iconField"
      :model-value="widget.icon ?? null"
      @update:model-value="updateWidget('icon', $event ?? undefined)"
    />
  </Field>
</template>
