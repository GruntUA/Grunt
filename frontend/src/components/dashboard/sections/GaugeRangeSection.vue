<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'

const { t } = useI18n()
const { widget, updateWidget } = useWidgetPropertyEditor()
</script>

<template>
  <div class="grid grid-cols-2 gap-2">
    <div class="space-y-1">
      <label class="font-medium text-muted-foreground uppercase tracking-wide">{{ t('Min') }}</label>
      <input
        :value="widget.min_value"
        type="number"
        class="w-full h-8 px-3 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
        @change="updateWidget('min_value', Number(($event.target as HTMLInputElement).value))"
      />
    </div>
    <div class="space-y-1">
      <label class="font-medium text-muted-foreground uppercase tracking-wide">{{ t('Max') }}</label>
      <input
        :value="widget.max_value"
        type="number"
        class="w-full h-8 px-3 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
        @change="updateWidget('max_value', Number(($event.target as HTMLInputElement).value))"
      />
    </div>
  </div>
</template>
