<script setup lang="ts">
import { provide, computed } from 'vue'

const props = defineProps<{ modelValue?: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

provide('$dropdownRadio', {
  modelValue: computed(() => props.modelValue),
  setValue: (v: string) => emit('update:modelValue', v),
})
</script>

<template>
  <div role="group" data-slot="dropdown-menu-radio-group">
    <slot />
  </div>
</template>
