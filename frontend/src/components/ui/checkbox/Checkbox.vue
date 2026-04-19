<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import PrimeCheckbox from 'primevue/checkbox'
import { cn } from "@/lib/utils"

const props = defineProps<{
  modelValue?: boolean | null
  checked?: boolean | null
  disabled?: boolean
  indeterminate?: boolean
  class?: HTMLAttributes["class"]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'update:checked': [value: boolean]
  'change': [event: Event]
}>()

function handleUpdate(val: boolean) {
  emit('update:modelValue', val)
  emit('update:checked', val)
}
</script>

<template>
  <PrimeCheckbox
    data-slot="checkbox"
    :binary="true"
    :model-value="!!(modelValue ?? checked)"
    :disabled="disabled"
    :indeterminate="indeterminate"
    :class="cn('', props.class)"
    @update:model-value="handleUpdate"
    @change="emit('change', $event)"
  />
</template>
