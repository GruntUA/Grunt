<script setup lang="ts">
import { ref, provide } from 'vue'

const isOpen = ref(false)
const triggerEl = ref<HTMLElement | null>(null)

provide('$dropdownSub', {
  isOpen,
  open: () => { isOpen.value = true },
  close: () => { isOpen.value = false },
  triggerEl,
})
</script>

<template>
  <slot />
</template>
