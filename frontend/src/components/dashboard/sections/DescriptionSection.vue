<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'

const { t } = useI18n()
const { widget, updateWidget } = useWidgetPropertyEditor()

const label = computed(() => widget.value.widget_type === 'clock' ? t('Note') : t('Subtitle'))
</script>

<template>
  <div class="space-y-1">
    <label class="font-medium text-muted-foreground uppercase tracking-wide">{{ label }}</label>
    <input
      :value="widget.description"
      class="w-full h-8 px-3 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
      @change="updateWidget('description', ($event.target as HTMLInputElement).value)"
    />
  </div>
</template>
