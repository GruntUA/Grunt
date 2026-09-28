<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import { useBuilderStore } from '@/stores/builder'
import { usePropertyEditor } from '@/core/composables/usePropertyEditor'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'

const { t } = useI18n()

const { field, updateField } = usePropertyEditor()
const builder = useBuilderStore()

const AGGREGATE_FUNCTIONS = [
  { value: '__none__', label: t('— no aggregation —') },
  { value: 'sum', label: t('sum — total') },
  { value: 'count', label: t('count — number of rows') },
  { value: 'avg', label: t('avg — average') },
  { value: 'min', label: t('min — minimum') },
  { value: 'max', label: t('max — maximum') },
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
    <p class="font-semibold text-muted-foreground uppercase tracking-wide">Aggregation</p>
    <span
      v-if="field.aggregate_function"
      class="font-mono text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800 px-1.5 py-0.5 rounded"
    >∑ {{ t('is active') }}</span>
  </div>
  <div class="flex flex-col gap-3 mb-4">
    <div class="flex flex-col gap-1.5">
      <label class="font-medium">{{ t('Function') }}</label>
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
        <label class="font-medium">{{ t('Table (TABLE field)') }}</label>
        <Select :model-value="field.aggregate_table ?? ''" :empty-message="t('No TABLE fields in this DocType')" @update:model-value="updateField('aggregate_table', $event || null)">
          <SelectTrigger class="w-full">
            <SelectValue :placeholder="t('— choose a TABLE field —')" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in tableFields" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div v-if="field.aggregate_function !== 'count'" class="flex flex-col gap-1.5">
        <label class="font-medium">{{ t('Child DocType field') }}</label>
        <Input
          :model-value="field.aggregate_field ?? ''"
          :placeholder="t('e.g. amount')"
          class="w-full"
          @update:model-value="updateField('aggregate_field', $event || null)"
        />
        <p class="text-muted-foreground">{{ t('Fieldname of a numeric field in the child DocType') }}</p>
      </div>
    </template>
  </div>
</template>
