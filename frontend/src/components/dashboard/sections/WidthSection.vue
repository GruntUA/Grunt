<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'

const { t } = useI18n()
const { widget, updateWidget } = useWidgetPropertyEditor()

const COLS = computed(() => [
  { value: 1, label: '1/4' },
  { value: 2, label: '1/2' },
  { value: 3, label: '3/4' },
  { value: 4, label: t('Full') },
])
</script>

<template>
  <div class="flex flex-col gap-1.5 mb-4">
    <label class="font-medium">{{ t('Width') }}</label>
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      class="w-full"
      :model-value="String(widget.cols)"
      @update:model-value="(v) => v && updateWidget('cols', Number(v))"
    >
      <ToggleGroupItem v-for="c in COLS" :key="c.value" :value="String(c.value)" class="flex-1">{{ c.label }}</ToggleGroupItem>
    </ToggleGroup>
  </div>
</template>
