<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import PrimeToggleSwitch from 'primevue/toggleswitch'
import { cn } from "@/lib/utils"

const props = defineProps<{
  modelValue?: boolean | null
  checked?: boolean | null
  disabled?: boolean
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
  <PrimeToggleSwitch
    data-slot="switch"
    :model-value="!!(modelValue ?? checked)"
    :disabled="disabled"
    :class="cn('', props.class)"
    @update:model-value="handleUpdate"
    @change="emit('change', $event)"
  />
</template>
