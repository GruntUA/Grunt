<script setup lang="ts">
import { computed } from 'vue'
import PrimeAccordion from 'primevue/accordion'

const props = defineProps<{
  type?: 'single' | 'multiple'
  collapsible?: boolean
  modelValue?: string | string[]
  class?: string
}>()
const emit = defineEmits<{ 'update:modelValue': [value: string | string[]] }>()

const multiple = props.type === 'multiple'

const accordionProps = computed(() => {
  const p: Record<string, any> = { multiple }
  if (props.modelValue !== undefined) p.value = props.modelValue
  return p
})
</script>

<template>
  <PrimeAccordion
    v-bind="accordionProps"
    @update:value="(v) => v != null && emit('update:modelValue', v)"
    data-slot="accordion"
    :class="props.class"
  >
    <slot />
  </PrimeAccordion>
</template>
