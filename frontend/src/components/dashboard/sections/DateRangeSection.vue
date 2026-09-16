<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
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
    <div class="space-y-1">
      <label class="font-medium text-muted-foreground uppercase tracking-wide">{{ t('Date field') }}</label>
      <input
        :value="widget.date_field"
        class="w-full h-8 px-3 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
        placeholder="created_at"
        @change="updateWidget('date_field', ($event.target as HTMLInputElement).value)"
      />
    </div>
    <div class="space-y-1">
      <label class="font-medium text-muted-foreground uppercase tracking-wide">{{ t('Period') }}</label>
      <div class="grid grid-cols-4 gap-1">
        <button
          v-for="p in PERIODS" :key="p.value"
          :class="[
            'py-1.5 rounded-md border transition-colors',
            widget.period === p.value ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-muted',
          ]"
          @click="updateWidget('period', p.value)"
        >{{ p.label }}</button>
      </div>
    </div>
  </template>
</template>
