<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { FormField } from '@/components/ui/form-field'
import { Loader2 } from '@lucide/vue'
import client from '@/core/api/client'

const router = useRouter()
const code = ref('')
const loading = ref(false)
const error = ref('')

async function handleVerify() {
  error.value = ''
  loading.value = true
  try {
    await client.post('/api/v1/auth/mfa/verify', { code: code.value })
    router.push('/')
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Invalid code. Try again.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-background p-6">
    <div class="w-full max-w-sm space-y-6">
      <div class="text-center">
        <h1 class="text-2xl font-semibold tracking-tight">Two-factor authentication</h1>
        <p class="text-sm text-muted-foreground mt-1">
          Enter the 6-digit code from your authenticator app, or a backup code.
        </p>
      </div>

      <form class="space-y-4" @submit.prevent="handleVerify">
        <FormField label="Authentication code">
          <Input
            v-model="code"
            placeholder="000000"
            maxlength="8"
            autocomplete="one-time-code"
            inputmode="numeric"
            class="text-center tracking-widest text-lg"
            autofocus
          />
        </FormField>

        <p v-if="error" class="text-sm text-destructive text-center">{{ error }}</p>

        <Button type="submit" class="w-full" :disabled="loading || !code">
          <Loader2 v-if="loading" class="mr-2 size-4 animate-spin" />
          Verify
        </Button>
      </form>
    </div>
  </div>
</template>
