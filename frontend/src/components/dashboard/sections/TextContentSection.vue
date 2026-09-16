<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'

const { t } = useI18n()
const { widget, updateWidget } = useWidgetPropertyEditor()
</script>

<template>
  <div class="space-y-1">
    <label class="font-medium text-muted-foreground uppercase tracking-wide">{{ t('Content (HTML/text)') }}</label>
    <textarea
      :value="widget.content"
      rows="5"
      class="w-full px-3 py-2 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none font-mono"
      @change="updateWidget('content', ($event.target as HTMLTextAreaElement).value)"
    />
  </div>
</template>
