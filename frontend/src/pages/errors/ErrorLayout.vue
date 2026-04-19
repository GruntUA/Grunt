<script setup lang="ts">
import { useRouter } from 'vue-router'

const props = withDefaults(defineProps<{
  code?: string | number
  title: string
  message: string
  showHomeButton?: boolean
  showBackButton?: boolean
}>(), {
  showHomeButton: false,
  showBackButton: false,
})

const router = useRouter()
</script>

<template>
  <div class="bg-background text-foreground min-h-screen flex items-center justify-center p-6">
    <div class="text-center max-w-md w-full">
      <p v-if="code" class="text-8xl font-bold text-muted-foreground/20 mb-4 select-none">{{ code }}</p>
      <h1 class="text-2xl font-semibold mb-2">{{ title }}</h1>
      <p class="text-sm text-muted-foreground mb-8">
        {{ message }}
      </p>
      <div class="flex gap-3 justify-center flex-wrap">
        <slot name="actions">
          <Button v-if="showBackButton" outlined @click="router.back()">Go back</Button>
          <Button v-if="showHomeButton" @click="router.push('/')">Go home</Button>
        </slot>
      </div>
    </div>
  </div>
</template>
