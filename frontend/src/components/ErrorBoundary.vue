<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, onErrorCaptured } from 'vue'
import { useRouter } from 'vue-router'
import ErrorLayout from '@/pages/errors/ErrorLayout.vue'
import { Button } from '@/components/ui/button'

const { t } = useI18n()
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
    :title="t('Something went wrong')"
    :message="errorMessage || t('An unexpected error occurred.')"
  >
    <template #actions>
      <Button variant="outline" @click="reset">{{ t('Try again') }}</Button>
      <Button @click="goHome">{{ t('Go home') }}</Button>
    </template>
  </ErrorLayout>
  <slot v-else />
</template>
