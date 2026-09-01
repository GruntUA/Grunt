<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DocField } from '@/types'
import { parseSelectValues } from '@/lib/selectOptions'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

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

const options = computed(() => parseSelectValues(props.field.options))
</script>

<template>
  <Select :model-value="modelValue" @update:model-value="(v: unknown) => emit('update:modelValue', String(v))">
    <SelectTrigger size="sm" class="h-8 text-xs w-full">
      <SelectValue :placeholder="t('Select value')" />
    </SelectTrigger>
    <SelectContent>
      <SelectItem v-for="opt in options" :key="opt" :value="opt">{{ opt }}</SelectItem>
    </SelectContent>
  </Select>
</template>
