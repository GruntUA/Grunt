<script setup lang="ts">
import { RouterView } from 'vue-router'
import { Toaster as Sonner } from '@/components/ui/sonner'
import GruntDialog from '@/components/desk/GruntDialog.vue'
</script>

<template>
  <RouterView />
  <Sonner />
  <GruntDialog />
</template>
