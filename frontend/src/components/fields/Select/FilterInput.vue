<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DocField } from '@/types'
import { parseSelectOptions } from '@/lib/selectOptions'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { MultiSelect } from '@/components/ui/multi-select'
import { MULTI_VALUE_OPS } from '@/core/api/docs'

const props = defineProps<{
  field: DocField
  modelValue: string
  displayValue: string
  op: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:displayValue': [value: string]
  'submit': []
}>()

const { t } = useI18n()

const options = computed(() => parseSelectOptions(props.field.options, props.field.option_labels))
const multi = computed(() => MULTI_VALUE_OPS.includes(props.op))
const values = computed(() => props.modelValue ? props.modelValue.split(',') : [])
</script>

<template>
  <MultiSelect
    v-if="multi"
    :model-value="values"
    :options="options"
    option-label="label"
    option-value="value"
    :placeholder="t('Select value')"
    class="h-8 text-xs w-full"
    @update:model-value="emit('update:modelValue', $event.join(','))"
  />
  <Select v-else :model-value="modelValue" @update:model-value="(v: unknown) => emit('update:modelValue', String(v))">
    <SelectTrigger size="sm" class="h-8 text-xs w-full">
      <SelectValue :placeholder="t('Select value')" />
    </SelectTrigger>
    <SelectContent>
      <SelectItem v-for="opt in options" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
    </SelectContent>
  </Select>
</template>
