<script setup lang="ts">
import { ref, computed, provide } from 'vue'

const props = defineProps<{
  open?: boolean
  modal?: boolean
}>()
const emit = defineEmits<{ 'update:open': [value: boolean] }>()

const internalOpen = ref(props.open ?? false)
const isOpen = computed({
  get: () => props.open !== undefined ? props.open : internalOpen.value,
  set: (v: boolean) => {
    internalOpen.value = v
    emit('update:open', v)
  }
})

provide('$sheet', {
  isOpen,
  open: () => { isOpen.value = true },
  close: () => { isOpen.value = false },
  modal: computed(() => props.modal ?? true),
})
</script>

<template>
  <slot />
</template>
