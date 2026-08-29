<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue'
import { useRouter } from 'vue-router'
import ErrorLayout from '@/pages/errors/ErrorLayout.vue'

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
  <ErrorLayout
    v-if="hasError"
    code="500"
    title="Something went wrong"
    :message="errorMessage || 'An unexpected error occurred.'"
  >
    <template #actions>
      <button
        class="px-4 py-2 rounded-md border border-input bg-background hover:bg-muted transition-colors"
        @click="reset"
      >
        Try again
      </button>
      <button
        class="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
        @click="goHome"
      >
        Go home
      </button>
    </template>
  </ErrorLayout>
  <slot v-else />
</template>
