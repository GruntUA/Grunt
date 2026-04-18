<script setup lang="ts">
import { computed } from 'vue'
import { useBuilderStore } from '@/stores/builder'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

const { field, updateField } = usePropertyEditor()
const builder = useBuilderStore()

const tableFields = computed(() =>
  (builder.doctype?.fields ?? []).filter((f) => f.fieldtype === 'Table')
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
        @update:model-value="updateField('aggregate_function', $event === '__none__' ? null : $event)"
      >
        <SelectTrigger><SelectValue placeholder="— без агрегації —" /></SelectTrigger>
        <SelectContent>
          <SelectItem value="__none__">— без агрегації —</SelectItem>
          <SelectItem value="sum">sum — сума</SelectItem>
          <SelectItem value="count">count — кількість рядків</SelectItem>
          <SelectItem value="avg">avg — середнє</SelectItem>
          <SelectItem value="min">min — мінімум</SelectItem>
          <SelectItem value="max">max — максимум</SelectItem>
        </SelectContent>
      </Select>
    </div>
    <template v-if="field.aggregate_function">
      <div class="space-y-1.5">
        <Label class="text-sm">Таблиця (TABLE поле)</Label>
        <Select
          :model-value="field.aggregate_table ?? ''"
          @update:model-value="updateField('aggregate_table', $event || null)"
        >
          <SelectTrigger><SelectValue placeholder="— оберіть TABLE поле —" /></SelectTrigger>
          <SelectContent>
            <SelectItem v-for="tf in tableFields" :key="tf.fieldname" :value="tf.fieldname">
              {{ tf.label || tf.fieldname }} ({{ tf.fieldname }})
            </SelectItem>
            <div v-if="!tableFields.length" class="px-2 py-1.5 text-xs text-muted-foreground">
              Немає TABLE полів у цьому DocType
            </div>
          </SelectContent>
        </Select>
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
