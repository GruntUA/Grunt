<script setup lang="ts">
import { computed } from 'vue'
import { useBuilderStore } from '@/stores/builder'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
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
  <Separator class="!mb-3" />
  <div class="flex items-center justify-between mb-3">
    <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Aggregation</p>
    <span
      v-if="field.aggregate_function"
      class="text-xs font-mono text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800 px-1.5 py-0.5 rounded"
    >∑ активна</span>
  </div>
  <div class="flex flex-col gap-3 mb-4">
    <div class="flex flex-col gap-1.5">
      <label class="text-sm font-medium">Функція</label>
      <Select :model-value="field.aggregate_function ?? '__none__'" @update:model-value="updateField('aggregate_function', $event === '__none__' ? null : $event)">
        <SelectTrigger class="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem v-for="opt in AGGREGATE_FUNCTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
        </SelectContent>
      </Select>
    </div>
    <template v-if="field.aggregate_function">
      <div class="flex flex-col gap-1.5">
        <label class="text-sm font-medium">Таблиця (TABLE поле)</label>
        <Select :model-value="field.aggregate_table ?? ''" empty-message="Немає TABLE полів у цьому DocType" @update:model-value="updateField('aggregate_table', $event || null)">
          <SelectTrigger class="w-full">
            <SelectValue placeholder="— оберіть TABLE поле —" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in tableFields" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div v-if="field.aggregate_function !== 'count'" class="flex flex-col gap-1.5">
        <label class="text-sm font-medium">Поле дочірнього DocType</label>
        <Input
          :model-value="field.aggregate_field ?? ''"
          placeholder="напр. amount"
          class="w-full"
          @update:model-value="updateField('aggregate_field', $event || null)"
        />
        <p class="text-xs text-muted-foreground">Fieldname числового поля у дочірньому DocType</p>
      </div>
    </template>
  </div>
</template>
