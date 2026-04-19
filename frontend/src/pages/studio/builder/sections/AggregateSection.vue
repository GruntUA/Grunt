<script setup lang="ts">
import { computed } from 'vue'
import { useBuilderStore } from '@/stores/builder'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'

const { field, updateField } = usePropertyEditor()
const builder = useBuilderStore()

const AGGREGATE_FUNCTIONS = [
  { value: '__none__', label: '— без агрегації —' },
  { value: 'sum', label: 'sum — сума' },
  { value: 'count', label: 'count — кількість рядків' },
  { value: 'avg', label: 'avg — середнє' },
  { value: 'min', label: 'min — мінімум' },
  { value: 'max', label: 'max — максимум' },
]

const tableFields = computed(() =>
  (builder.doctype?.fields ?? []).filter((f) => f.fieldtype === 'Table').map(f => ({
    value: f.fieldname,
    label: `${f.label || f.fieldname} (${f.fieldname})`,
  }))
)
</script>

<template>
  <Separator class="mb-3" />
  <div class="flex items-center justify-between mb-3">
    <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Aggregation</p>
    <span
      v-if="field.aggregate_function"
      class="text-[10px] font-mono text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800 px-1.5 py-0.5 rounded"
    >∑ активна</span>
  </div>
  <div class="flex flex-col gap-3 mb-4">
    <div class="space-y-1.5">
      <Label class="text-sm">Функція</Label>
      <Select
        :model-value="field.aggregate_function ?? '__none__'"
        :options="AGGREGATE_FUNCTIONS"
        option-label="label"
        option-value="value"
        class="w-full"
        @update:model-value="updateField('aggregate_function', $event === '__none__' ? null : $event)"
      />
    </div>
    <template v-if="field.aggregate_function">
      <div class="space-y-1.5">
        <Label class="text-sm">Таблиця (TABLE поле)</Label>
        <Select
          :model-value="field.aggregate_table ?? ''"
          :options="tableFields"
          option-label="label"
          option-value="value"
          placeholder="— оберіть TABLE поле —"
          empty-message="Немає TABLE полів у цьому DocType"
          class="w-full"
          @update:model-value="updateField('aggregate_table', $event || null)"
        />
      </div>
      <div v-if="field.aggregate_function !== 'count'" class="space-y-1.5">
        <Label class="text-sm">Поле дочірнього DocType</Label>
        <Input
          :model-value="field.aggregate_field ?? ''"
          placeholder="напр. amount"
          @update:model-value="updateField('aggregate_field', $event || null)"
        />
        <p class="text-[11px] text-muted-foreground">Fieldname числового поля у дочірньому DocType</p>
      </div>
    </template>
  </div>
</template>
