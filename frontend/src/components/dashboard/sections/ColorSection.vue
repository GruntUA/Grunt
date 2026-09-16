<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'
import { WIDGET_COLORS, WIDGET_COLOR_LABEL_KEYS } from './widgetHelpers'

const { t } = useI18n()
const { widget, updateWidget } = useWidgetPropertyEditor()
</script>

<template>
  <div class="space-y-1">
    <label class="font-medium text-muted-foreground uppercase tracking-wide">{{ t('Color') }}</label>
    <div class="flex gap-2">
      <button
        v-for="c in WIDGET_COLORS" :key="c.value"
        :title="t(WIDGET_COLOR_LABEL_KEYS[c.value])"
        :class="['w-7 h-7 rounded-full border-2 transition-colors', widget.color === c.value ? 'border-foreground scale-110' : 'border-transparent']"
        :style="{ background: c.bg }"
        @click="updateWidget('color', c.value)"
      />
    </div>
  </div>
</template>
