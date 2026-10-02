<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { DocField } from '@/types'
import { Input } from '@/components/ui/input'
import { MULTI_VALUE_OPS } from '@/core/api/docs'

const { t } = useI18n()

defineProps<{
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
</script>

<template>
  <Input
    :model-value="modelValue"
    class="w-full"
    :placeholder="op === 'like' ? t('part of the text...') : MULTI_VALUE_OPS.includes(op) ? t('comma-separated values') : t('Value')"
    @update:model-value="emit('update:modelValue', String($event))"
    @keydown.enter="emit('submit')"
  />
</template>
