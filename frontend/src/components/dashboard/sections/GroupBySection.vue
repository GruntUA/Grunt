<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'
import { isReportSourced } from './widgetHelpers'

const { t } = useI18n()
const { widget, updateWidget } = useWidgetPropertyEditor()
</script>

<template>
  <div v-if="!isReportSourced(widget)" class="space-y-1">
    <label class="font-medium text-muted-foreground uppercase tracking-wide">{{ t('Group by') }}</label>
    <input
      :value="widget.group_by"
      class="w-full h-8 px-3 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
      placeholder="fieldname"
      @change="updateWidget('group_by', ($event.target as HTMLInputElement).value)"
    />
  </div>
</template>
