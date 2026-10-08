<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
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
  <Separator class="!mb-3" />
  <p class="font-semibold text-muted-foreground uppercase tracking-wide mb-3">{{ t('Aggregation') }}</p>
  <div class="mb-4">
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      orientation="vertical"
      :spacing="1"
      class="w-full flex-col items-stretch"
      :model-value="widget.aggregation"
      @update:model-value="(v) => v && updateWidget('aggregation', v)"
    >
      <ToggleGroupItem v-for="a in AGGREGATIONS" :key="a.value" :value="a.value" class="w-full justify-start">{{ a.label }}</ToggleGroupItem>
    </ToggleGroup>
  </div>
  <div v-if="needsField" class="flex flex-col gap-1.5 mb-4">
    <label class="font-medium">{{ t('Field') }}</label>
    <Input
      :model-value="widget.field ?? ''"
      placeholder="fieldname"
      class="w-full"
      @update:model-value="updateWidget('field', $event)"
    />
  </div>
  <template v-if="widget.widget_type === 'table'">
    <div class="flex flex-col gap-1.5 mb-4">
      <label class="font-medium">{{ t('Value label') }}</label>
      <Input
        :model-value="widget.value_label ?? ''"
        :placeholder="AGGREGATIONS.find((a) => a.value === widget.aggregation)?.label"
        class="w-full"
        @update:model-value="updateWidget('value_label', $event || null)"
      />
    </div>
    <div class="flex flex-col gap-1.5 mb-4">
      <label class="font-medium">{{ t('Rows') }}</label>
      <Input
        type="number"
        min="1"
        max="100"
        :model-value="widget.row_limit ?? ''"
        placeholder="20"
        class="w-full"
        @update:model-value="updateWidget('row_limit', $event ? Number($event) : null)"
      />
    </div>
  </template>
</template>
