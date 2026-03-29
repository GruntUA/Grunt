<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const hasError = ref(false)
const errorMessage = ref('')

onErrorCaptured((err: unknown) => {
  hasError.value = true
  errorMessage.value = err instanceof Error ? err.message : String(err)
  return false // prevent propagation
})

function reset() {
  hasError.value = false
  errorMessage.value = ''
}

function goHome() {
  reset()
  router.push('/')
}
</script>

<template>
  <div v-if="hasError" class="min-h-screen flex items-center justify-center p-6">
    <div class="text-center max-w-md">
      <p class="text-6xl font-bold text-muted-foreground/30 mb-4">500</p>
      <h1 class="text-xl font-semibold text-foreground mb-2">Something went wrong</h1>
      <p class="text-sm text-muted-foreground mb-6">{{ errorMessage || 'An unexpected error occurred.' }}</p>
      <div class="flex gap-3 justify-center">
        <button
          class="px-4 py-2 text-sm rounded-md border border-input bg-background hover:bg-muted transition-colors"
          @click="reset"
        >
          Try again
        </button>
        <button
          class="px-4 py-2 text-sm rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
          @click="goHome"
        >
          Go home
        </button>
      </div>
    </div>
  </div>
  <slot v-else />
</template>
