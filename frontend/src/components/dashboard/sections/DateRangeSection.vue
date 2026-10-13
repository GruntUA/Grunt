<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useId } from 'vue'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Field, FieldLabel } from '@/components/ui/field'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'
import { isReportSourced } from './widgetHelpers'
import { useWidgetPeriods } from '@/core/widgetPeriod'

const { t } = useI18n()
const id = useId()
const { widget, updateWidget } = useWidgetPropertyEditor()

const PERIODS = useWidgetPeriods()
</script>

<template>
  <template v-if="!isReportSourced(widget)">
    <Field class="mb-4">
      <FieldLabel :for="`${id}-1`">{{ t('Date field') }}</FieldLabel>
      <Input
        :id="`${id}-1`"
        :model-value="widget.date_field ?? ''"
        placeholder="created_at"
        class="w-full"
        @update:model-value="updateWidget('date_field', $event)"
      />
    </Field>
    <Field class="mb-4">
      <FieldLabel>{{ t('Period') }}</FieldLabel>
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
    </Field>
    <Field v-if="widget.widget_type === 'table'" orientation="horizontal" class="mb-4 justify-between">
      <FieldLabel :for="`${id}-period-switch`">{{ t('Period switcher') }}</FieldLabel>
      <Switch
        :id="`${id}-period-switch`"
        :model-value="!!widget.period_switch"
        @update:model-value="updateWidget('period_switch', $event)"
      />
    </Field>
  </template>
</template>
