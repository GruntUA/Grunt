<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'

const { t } = useI18n()
const { widget, updateWidget } = useWidgetPropertyEditor()

const AGGREGATIONS = computed(() => [
  { value: 'count', label: t('Count (COUNT)') },
  { value: 'sum',   label: t('Sum (SUM)') },
  { value: 'avg',   label: t('Average (AVG)') },
  { value: 'min',   label: t('Minimum') },
  { value: 'max',   label: t('Maximum') },
])

const needsField = computed(() => ['sum', 'avg', 'min', 'max'].includes(widget.value.aggregation))
</script>

<template>
  <div class="space-y-1">
    <label class="font-medium text-muted-foreground uppercase tracking-wide">{{ t('Aggregation') }}</label>
    <div class="grid grid-cols-1 gap-1">
      <button
        v-for="a in AGGREGATIONS" :key="a.value"
        :class="[
          'px-3 py-1.5 rounded-md border transition-colors text-left',
          widget.aggregation === a.value ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-muted',
        ]"
        @click="updateWidget('aggregation', a.value)"
      >{{ a.label }}</button>
    </div>
  </div>
  <div v-if="needsField" class="space-y-1">
    <label class="font-medium text-muted-foreground uppercase tracking-wide">{{ t('Field') }}</label>
    <input
      :value="widget.field"
      class="w-full h-8 px-3 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
      placeholder="fieldname"
      @change="updateWidget('field', ($event.target as HTMLInputElement).value)"
    />
  </div>
</template>
