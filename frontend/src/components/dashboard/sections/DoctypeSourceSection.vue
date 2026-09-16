<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useDocTypeStore } from '@/stores/doctype'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'
import { isReportSourced } from './widgetHelpers'

const { t } = useI18n()
const dtStore = useDocTypeStore()
const { widget, updateWidget } = useWidgetPropertyEditor()
</script>

<template>
  <div v-if="!isReportSourced(widget)" class="space-y-1">
    <label class="font-medium text-muted-foreground uppercase tracking-wide">DocType</label>
    <select
      :value="widget.doctype"
      class="w-full h-8 px-3 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
      @change="updateWidget('doctype', ($event.target as HTMLSelectElement).value)"
    >
      <option value="">{{ t('— Select —') }}</option>
      <option v-for="dt in dtStore.doctypes.filter(d => !d.is_child)" :key="dt.name" :value="dt.name">
        {{ dt.label }}
      </option>
    </select>
  </div>
</template>
