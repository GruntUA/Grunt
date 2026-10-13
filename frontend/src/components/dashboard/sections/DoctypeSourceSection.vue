<script setup lang="ts">
import { computed } from 'vue'
import { useDocTypeStore } from '@/stores/doctype'
import DocTypeCombobox from '@/components/DocTypeCombobox.vue'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'
import { isReportSourced } from './widgetHelpers'

const dtStore = useDocTypeStore()
const { widget, updateWidget } = useWidgetPropertyEditor()

const doctypeNames = computed(() => dtStore.doctypes.filter(d => !d.is_child).map(d => d.name))
</script>

<template>
  <Field v-if="!isReportSourced(widget)" class="mb-4">
    <FieldLabel>DocType</FieldLabel>
    <DocTypeCombobox
      :model-value="widget.ref_doctype"
      :options="doctypeNames"
      class="w-full"
      @update:model-value="updateWidget('ref_doctype', $event)"
    />
  </Field>
</template>
