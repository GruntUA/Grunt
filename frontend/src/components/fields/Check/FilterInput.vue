<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { DocField } from '@/types'

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
  <div class="flex gap-2">
    <button
      type="button"
      class="flex-1 py-1.5 rounded border transition-colors"
      :class="modelValue === '1'
        ? 'border-primary bg-primary/10 text-primary font-semibold'
        : 'border-border hover:border-primary/40 text-muted-foreground'"
      @click="emit('update:modelValue', '1')"
    >✓ {{ t('Yes') }}</button>
    <button
      type="button"
      class="flex-1 py-1.5 rounded border transition-colors"
      :class="modelValue === '0'
        ? 'border-primary bg-primary/10 text-primary font-semibold'
        : 'border-border hover:border-primary/40 text-muted-foreground'"
      @click="emit('update:modelValue', '0')"
    >✗ {{ t('No') }}</button>
  </div>
</template>
