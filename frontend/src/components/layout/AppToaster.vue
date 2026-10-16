<script setup lang="ts">
import { computed } from 'vue'
import { useColorMode } from '@/core/composables/useColorMode'
import { useTaskTracker } from '@/core/composables/useTaskTracker'
import { Toaster } from '@/components/ui/sonner'

const { isDark } = useColorMode()

// Toasts stack above the background-task panel (both live bottom-right).
const taskPanelHeight = useTaskTracker().panelHeight
const offset = computed(() =>
  taskPanelHeight.value ? { bottom: 24 + taskPanelHeight.value + 8 } : undefined)
</script>

<template>
  <Toaster position="bottom-right" :theme="isDark ? 'dark' : 'light'"
    :offset="offset" :mobile-offset="offset" />
</template>
