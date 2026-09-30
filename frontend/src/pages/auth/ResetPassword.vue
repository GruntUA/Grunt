<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { authApi } from '@/core/api/auth-admin'
import { Sprout } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'

const { t } = useI18n()

const router = useRouter()
const route = useRoute()

const token = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const done = ref(false)
const error = ref('')

onMounted(() => {
  token.value = (route.query.token as string) ?? ''
  if (!token.value) {
    error.value = t('Invalid or missing reset token.')
  }
})

async function handleSubmit() {
  error.value = ''
  if (newPassword.value !== confirmPassword.value) {
    error.value = t('Passwords do not match')
    return
  }
  if (newPassword.value.length < 8) {
    error.value = t('Password must be at least 8 characters')
    return
  }
  loading.value = true
  try {
    await authApi.resetPassword(token.value, newPassword.value)
    done.value = true
  } catch (e: any) {
    const body = e?.response?.data
    const detail = body?.error?.message ?? body?.detail
    if (typeof detail === 'string') {
      error.value = detail
    } else {
      error.value = e?.message || t('Something went wrong')
    }
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
        <h1 class="text-2xl font-semibold text-foreground tracking-tight">{{ t('New password') }}</h1>
        <p class="text-muted-foreground mt-1">{{ t('Choose a strong password') }}</p>
      </div>

      <div class="bg-card rounded-lg shadow-sm border border-border p-8">
        <div v-if="done" class="text-center py-4 flex flex-col items-center gap-3">
          <p class="text-foreground font-medium">{{ t('Password updated!') }}</p>
          <p class="text-muted-foreground mb-2">{{ t('You can now sign in with your new password.') }}</p>
          <Button class="w-full h-11" @click="router.push('/login')">{{ t('Go to sign in') }}</Button>
        </div>

        <form v-else class="flex flex-col gap-5" @submit.prevent="handleSubmit">
          <div class="flex flex-col gap-1.5">
            <label class="font-medium">{{ t('New password') }} <span class="text-destructive">*</span></label>
            <Input v-model="newPassword" type="password" autocomplete="new-password"
              placeholder="••••••••" required class="h-11 w-full" />
          </div>

          <div class="flex flex-col gap-1.5">
            <label class="font-medium">{{ t('Confirm password') }} <span class="text-destructive">*</span></label>
            <Input v-model="confirmPassword" type="password" autocomplete="new-password"
              placeholder="••••••••" required class="h-11 w-full" />
          </div>

          <p v-if="error" class="text-destructive bg-destructive/10 rounded-lg px-3 py-2 text-center border border-destructive/20">
            {{ error }}
          </p>

          <Button
            type="submit"
            :disabled="loading || !token"
            class="w-full h-11 mt-1 font-medium"
          >
            <Spinner v-if="loading" class="size-4 mr-2" />
            {{ t('Set new password') }}
          </Button>
        </form>
      </div>
    </div>
  </div>
</template>
