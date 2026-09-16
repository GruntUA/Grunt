<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Input } from '@/components/ui/input'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'
import { isReportSourced } from './widgetHelpers'

const { t } = useI18n()
const { widget, updateWidget } = useWidgetPropertyEditor()

const PERIODS = computed(() => [
  { value: '7d',   label: t('7 days') },
  { value: '30d',  label: t('30 days') },
  { value: '90d',  label: t('3 months') },
  { value: '365d', label: t('Year') },
])
</script>

<template>
  <template v-if="!isReportSourced(widget)">
    <div class="flex flex-col gap-1.5 mb-4">
      <label class="font-medium">{{ t('Date field') }}</label>
      <Input
        :model-value="widget.date_field ?? ''"
        placeholder="created_at"
        class="w-full"
        @update:model-value="updateWidget('date_field', $event)"
      />
    </div>
    <div class="flex flex-col gap-1.5 mb-4">
      <label class="font-medium">{{ t('Period') }}</label>
      <ToggleGroup
        type="single"
        variant="outline"
        size="sm"
        class="w-full"
        :model-value="widget.period"
        @update:model-value="(v) => v && updateWidget('period', v)"
      >
        <ToggleGroupItem v-for="p in PERIODS" :key="p.value" :value="p.value" class="flex-1">{{ p.label }}</ToggleGroupItem>
      </ToggleGroup>
    </div>
  </template>
</template>
