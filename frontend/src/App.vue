<script setup lang="ts">
import { RouterView } from 'vue-router'
import { Toaster as Sonner } from '@/components/ui/sonner'
import GruntDialog from '@/components/desk/GruntDialog.vue'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import CommandPalette from '@/components/layout/CommandPalette.vue'
</script>

<template>
  <ErrorBoundary>
    <RouterView />
    <Sonner />
    <GruntDialog />
    <CommandPalette />
  </ErrorBoundary>
</template>
