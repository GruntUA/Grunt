<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'
import { WIDGET_COLORS, WIDGET_COLOR_LABEL_KEYS } from './widgetHelpers'

const { t } = useI18n()
const { widget, updateWidget } = useWidgetPropertyEditor()
</script>

<template>
  <div class="flex flex-col gap-1.5 mb-4">
    <label class="font-medium">{{ t('Color') }}</label>
    <ToggleGroup
      type="single"
      variant="outline"
      class="w-fit"
      :model-value="widget.color"
      @update:model-value="(v) => v && updateWidget('color', v)"
    >
      <ToggleGroupItem
        v-for="c in WIDGET_COLORS" :key="c.value" :value="c.value"
        :title="t(WIDGET_COLOR_LABEL_KEYS[c.value])"
        :aria-label="t(WIDGET_COLOR_LABEL_KEYS[c.value])"
        class="p-1.5"
      >
        <span class="size-4 rounded-full" :style="{ background: c.bg }" />
      </ToggleGroupItem>
    </ToggleGroup>
  </div>
</template>
