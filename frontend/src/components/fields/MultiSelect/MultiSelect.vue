<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { BaseFieldProps } from '@/types'
import { cn } from '@/lib/utils'
import { parseSelectValues } from '@/lib/selectOptions'
import { MultiSelect as ShadcnMultiSelect } from '@/components/ui/multi-select'

const props = defineProps<BaseFieldProps>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const { t } = useI18n()

const parsedOptions = computed(() => parseSelectValues(props.field.options))

const selectedValues = computed<string[]>(() => {
  const v = props.modelValue
  if (Array.isArray(v)) return v.map(String)
  if (typeof v === 'string' && v) {
    try {
      const parsed = JSON.parse(v)
      return Array.isArray(parsed) ? parsed.map(String) : []
    } catch {
      return []
    }
  }
  return []
})

const triggerClass = computed(() =>
  cn(
    'w-full',
    props.error && 'border-destructive focus-visible:border-destructive focus-visible:ring-destructive/30',
    props.field.bold && 'font-medium',
  ),
)
</script>

<template>
  <ShadcnMultiSelect
    :model-value="selectedValues"
    :options="parsedOptions"
    :disabled="disabled || field.read_only"
    :placeholder="field.placeholder ?? t('— select —')"
    :aria-invalid="error ? true : undefined"
    :aria-label="field.label"
    :class="triggerClass"
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>
