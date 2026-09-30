<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { authApi } from '@/core/api/auth-admin'
import { Sprout, ArrowLeft } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'

const { t } = useI18n()

const router = useRouter()

const email = ref('')
const loading = ref(false)
const sent = ref(false)
const error = ref('')

async function handleSubmit() {
  error.value = ''
  loading.value = true
  try {
    await authApi.forgotPassword(email.value)
    sent.value = true
  } catch (e: any) {
    error.value = e?.response?.data?.error?.message || e?.response?.data?.detail || e?.message || 'Something went wrong'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-muted/30 relative overflow-hidden">

    <div class="relative w-full max-w-[420px] mx-4">
      <div class="text-center mb-8 flex flex-col items-center">
        <div class="inline-flex items-center justify-center w-14 h-14 rounded-lg bg-primary text-primary-foreground mb-4 shadow-sm">
          <Sprout class="w-7 h-7" />
        </div>
        <h1 class="text-2xl font-semibold text-foreground tracking-tight">{{ t('Reset password') }}</h1>
        <p class="text-muted-foreground mt-1">{{ t('We will send you a recovery link') }}</p>
      </div>

      <div class="bg-card rounded-lg shadow-sm border border-border p-8">
        <div v-if="sent" class="text-center py-4 flex flex-col items-center gap-3">
          <p class="text-foreground font-medium">{{ t('Check your email') }}</p>
          <p class="text-muted-foreground">
            {{ t('If an account with {email} exists, we have sent a password reset link.', { email }) }}
          </p>
          <Button variant="ghost" class="mt-2" @click="router.push('/login')">{{ t('Back to sign in') }}</Button>
        </div>

        <form v-else class="flex flex-col gap-5" @submit.prevent="handleSubmit">
          <div class="flex flex-col gap-1.5">
            <label class="font-medium">Email <span class="text-destructive">*</span></label>
            <Input v-model="email" type="email" placeholder="you@example.com" required class="h-11 w-full" />
          </div>

          <p v-if="error" class="text-destructive bg-destructive/10 rounded-lg px-3 py-2 text-center border border-destructive/20">
            {{ error }}
          </p>

          <Button type="submit" :disabled="loading" class="w-full h-11 mt-1 font-medium">
            <Spinner v-if="loading" class="size-4 mr-2" />
            {{ t('Send link') }}
          </Button>

          <button
            type="button"
            class="flex items-center justify-center gap-1.5 text-muted-foreground hover:text-foreground transition-colors mt-2"
            @click="router.push('/login')"
          >
            <ArrowLeft class="size-3.5" />
            {{ t('Back to sign in') }}
          </button>
        </form>
      </div>
    </div>
  </div>
</template>
