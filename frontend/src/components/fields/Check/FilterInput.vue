<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Check, X } from '@lucide/vue'
import type { DocField } from '@/types'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'

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
  <ToggleGroup
    type="single"
    variant="outline"
    class="w-full"
    :model-value="modelValue"
    @update:model-value="(v) => emit('update:modelValue', String(v ?? ''))"
  >
    <ToggleGroupItem value="1" class="flex-1"><Check /> {{ t('Yes') }}</ToggleGroupItem>
    <ToggleGroupItem value="0" class="flex-1"><X /> {{ t('No') }}</ToggleGroupItem>
  </ToggleGroup>
</template>
