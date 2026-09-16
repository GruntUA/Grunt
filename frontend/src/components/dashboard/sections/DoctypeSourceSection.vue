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
  <div v-if="!isReportSourced(widget)" class="flex flex-col gap-1.5 mb-4">
    <label class="font-medium">DocType</label>
    <DocTypeCombobox
      :model-value="widget.doctype"
      :options="doctypeNames"
      class="w-full"
      @update:model-value="updateWidget('doctype', $event)"
    />
  </div>
</template>
