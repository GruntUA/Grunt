<script setup lang="ts">
import { ref, computed, provide } from 'vue'

const props = defineProps<{
  open?: boolean
  defaultOpen?: boolean
}>()
const emit = defineEmits<{ 'update:open': [v: boolean] }>()

const internalOpen = ref(props.defaultOpen ?? false)
const isOpen = computed({
  get: () => props.open !== undefined ? props.open : internalOpen.value,
  set: (v: boolean) => { internalOpen.value = v; emit('update:open', v) },
})

const triggerEl = ref<HTMLElement | null>(null)

provide('$popover', {
  isOpen,
  triggerEl,
  toggle: () => { isOpen.value = !isOpen.value },
  close: () => { isOpen.value = false },
  setTrigger: (el: HTMLElement) => { triggerEl.value = el },
})
</script>

<template><slot /></template>
