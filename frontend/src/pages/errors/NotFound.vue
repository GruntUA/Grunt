<script setup lang="ts">
import { useRouter } from 'vue-router'
import { Button } from '@/components/ui/button'

const router = useRouter()
</script>

<template>
  <div class="min-h-screen flex items-center justify-center p-6">
    <div class="text-center max-w-md">
      <p class="text-8xl font-bold text-muted-foreground/20 mb-4 select-none">404</p>
      <h1 class="text-2xl font-semibold text-foreground mb-2">Page not found</h1>
      <p class="text-sm text-muted-foreground mb-8">
        The page you're looking for doesn't exist or has been moved.
      </p>
      <Button @click="router.push('/')">Go home</Button>
    </div>
  </div>
</template>
