<script setup lang="ts">
import { RouterView } from 'vue-router'
import { Toaster as Sonner } from '@/components/ui/sonner'
import GruntDialog from '@/components/desk/GruntDialog.vue'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
</script>

<template>
  <ErrorBoundary>
    <RouterView />
    <Sonner />
    <GruntDialog />
  </ErrorBoundary>
</template>
