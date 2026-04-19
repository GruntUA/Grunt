<script setup lang="ts">
import { computed, ref } from 'vue'
import type { HTMLAttributes } from 'vue'
import PrimeTabs from 'primevue/tabs'
import { cn } from '@/lib/utils'

const props = defineProps<{
  modelValue?: string
  defaultValue?: string
  class?: HTMLAttributes['class']
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const internalValue = ref(props.defaultValue ?? props.modelValue ?? '')

const value = computed({
  get: () => props.modelValue !== undefined ? props.modelValue : internalValue.value,
  set: (v: string) => {
    internalValue.value = v
    emit('update:modelValue', v)
  },
})
</script>

<template>
  <PrimeTabs
    v-model:value="value"
    :class="cn('', props.class)"
    data-slot="tabs"
  >
    <slot />
  </PrimeTabs>
</template>
