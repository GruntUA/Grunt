<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { authApi } from '@/core/api/auth-admin'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { FormField } from '@/components/ui/form-field'
import { Loader2, Sprout } from '@lucide/vue'

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
    error.value = 'Invalid or missing reset token.'
  }
})

async function handleSubmit() {
  error.value = ''
  if (newPassword.value !== confirmPassword.value) {
    error.value = 'Passwords do not match'
    return
  }
  if (newPassword.value.length < 8) {
    error.value = 'Password must be at least 8 characters'
    return
  }
  loading.value = true
  try {
    await authApi.resetPassword(token.value, newPassword.value)
    done.value = true
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    if (typeof detail === 'string') {
      error.value = detail
    } else {
      error.value = e?.message || 'Something went wrong'
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gradient-to-br from-emerald-50 via-background to-emerald-50/30 relative overflow-hidden">
    <div class="absolute inset-0 overflow-hidden pointer-events-none">
      <div class="absolute -top-24 -right-24 w-96 h-96 bg-emerald-100/40 rounded-full blur-3xl" />
      <div class="absolute -bottom-32 -left-32 w-[500px] h-[500px] bg-emerald-50/60 rounded-full blur-3xl" />
    </div>

    <div class="relative w-full max-w-[420px] mx-4">
      <div class="text-center mb-8">
        <div class="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-primary text-primary-foreground mb-4 shadow-lg shadow-primary/20">
          <Sprout class="w-7 h-7" />
        </div>
        <h1 class="text-2xl font-bold text-foreground tracking-tight">Set new password</h1>
        <p class="text-sm text-muted-foreground mt-1">Choose a strong password</p>
      </div>

      <div class="bg-card rounded-xl shadow-xl shadow-black/[0.04] border border-border/60 p-8">
        <div v-if="done" class="text-center py-4">
          <p class="text-sm text-foreground font-medium mb-2">Password updated!</p>
          <p class="text-sm text-muted-foreground mb-4">You can now sign in with your new password.</p>
          <Button class="w-full h-11" @click="router.push('/login')">
            Go to login
          </Button>
        </div>

        <form v-else class="flex flex-col gap-5" @submit.prevent="handleSubmit">
          <FormField label="New password" required>
            <template #default="{ id }">
              <Input
                :id="id"
                v-model="newPassword"
                type="password"
                autocomplete="new-password"
                placeholder="••••••••"
                required
                class="h-11"
              />
            </template>
          </FormField>

          <FormField label="Confirm password" required>
            <template #default="{ id }">
              <Input
                :id="id"
                v-model="confirmPassword"
                type="password"
                autocomplete="new-password"
                placeholder="••••••••"
                required
                class="h-11"
              />
            </template>
          </FormField>

          <div v-if="error" class="text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2 text-center">
            {{ error }}
          </div>

          <Button
            type="submit"
            :disabled="loading || !token"
            class="w-full h-11 mt-1 text-[15px] font-medium"
          >
            <Loader2 v-if="loading" class="mr-2 h-4 w-4 animate-spin" />
            Set new password
          </Button>
        </form>
      </div>
    </div>
  </div>
</template>
