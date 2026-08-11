<script setup lang="ts">
import { computed } from 'vue'
import type { BaseFieldProps } from '@/types'
import { Select as ShadcnSelect } from '@/components/ui/select'
import { SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

const props = defineProps<BaseFieldProps>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const parsedOptions = computed(() =>
  typeof props.field.options === 'string'
    ? props.field.options.split('\n').map(o => o.trim()).filter(Boolean)
    : (props.field.options ?? [])
)
</script>

<template>
  <ShadcnSelect
    :model-value="String(modelValue ?? '')"
    :disabled="disabled || field.read_only"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <SelectTrigger class="w-full">
      <SelectValue placeholder="— оберіть —" />
    </SelectTrigger>
    <SelectContent>
      <SelectItem v-for="opt in parsedOptions" :key="opt" :value="opt">{{ opt }}</SelectItem>
    </SelectContent>
  </ShadcnSelect>
</template>
