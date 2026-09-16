<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'

const { t } = useI18n()
const { widget, updateWidget } = useWidgetPropertyEditor()
</script>

<template>
  <div class="space-y-1">
    <label class="font-medium text-muted-foreground uppercase tracking-wide">{{ t('Icon (lucide)') }}</label>
    <input
      :value="widget.icon"
      class="w-full h-8 px-3 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
      placeholder="BarChart2, Users..."
      @change="updateWidget('icon', ($event.target as HTMLInputElement).value)"
    />
  </div>
</template>
