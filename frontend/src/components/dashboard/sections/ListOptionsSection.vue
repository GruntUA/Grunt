<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useId } from 'vue'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Field, FieldLabel } from '@/components/ui/field'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'

const { t } = useI18n()
const id = useId()
const { widget, updateWidget } = useWidgetPropertyEditor()
</script>

<template>
  <Separator class="!mb-3" />
  <p class="font-semibold text-muted-foreground uppercase tracking-wide mb-3">{{ t('Sorting') }}</p>
  <Field class="mb-4">
    <FieldLabel :for="`${id}-sort`">{{ t('Sort by') }}</FieldLabel>
    <Input
      :id="`${id}-sort`"
      :model-value="widget.sort_by ?? ''"
      placeholder="modified_at"
      class="w-full"
      @update:model-value="updateWidget('sort_by', $event || null)"
    />
  </Field>
  <Field class="mb-4">
    <FieldLabel>{{ t('Sort order') }}</FieldLabel>
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      class="w-full"
      :model-value="widget.sort_order || 'desc'"
      @update:model-value="(v) => v && updateWidget('sort_order', v)"
    >
      <ToggleGroupItem value="desc" class="flex-1">{{ t('Descending') }}</ToggleGroupItem>
      <ToggleGroupItem value="asc" class="flex-1">{{ t('Ascending') }}</ToggleGroupItem>
    </ToggleGroup>
  </Field>
  <Field class="mb-4">
    <FieldLabel :for="`${id}-date`">{{ t('Date field') }}</FieldLabel>
    <Input
      :id="`${id}-date`"
      :model-value="widget.date_field ?? ''"
      placeholder="modified_at"
      class="w-full"
      @update:model-value="updateWidget('date_field', $event || null)"
    />
  </Field>
  <Field class="mb-4">
    <FieldLabel :for="`${id}-rows`">{{ t('Rows') }}</FieldLabel>
    <Input
      :id="`${id}-rows`"
      type="number"
      min="1"
      max="50"
      :model-value="widget.row_limit ?? ''"
      placeholder="8"
      class="w-full"
      @update:model-value="updateWidget('row_limit', $event ? Number($event) : null)"
    />
  </Field>
</template>
