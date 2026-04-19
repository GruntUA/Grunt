<script setup lang="ts">
import { ref, provide } from 'vue'

const referenceEl = ref<Element | null>(null)
const isOpen = ref(false)

provide('$tooltip', { referenceEl, isOpen })
</script>

<template>
  <slot />
</template>
