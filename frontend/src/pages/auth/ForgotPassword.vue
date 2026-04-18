<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { authApi } from '@/core/api/auth-admin'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Field, FieldLabel } from '@/components/ui/field'
import { Loader2, Sprout, ArrowLeft } from '@lucide/vue'

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
    error.value = e?.response?.data?.detail || e?.message || 'Something went wrong'
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
        <h1 class="text-2xl font-bold text-foreground tracking-tight">Reset password</h1>
        <p class="text-sm text-muted-foreground mt-1">We'll send you a reset link</p>
      </div>

      <div class="bg-card rounded-xl shadow-xl shadow-black/[0.04] border border-border/60 p-8">
        <div v-if="sent" class="text-center py-4">
          <p class="text-sm text-foreground font-medium mb-2">Check your email</p>
          <p class="text-sm text-muted-foreground">
            If an account with <strong>{{ email }}</strong> exists, we've sent a password reset link.
          </p>
          <Button variant="link" class="mt-4" @click="router.push('/login')">
            Back to login
          </Button>
        </div>

        <form v-else class="flex flex-col gap-5" @submit.prevent="handleSubmit">
          <Field>
            <FieldLabel>Email <span class="text-destructive">*</span></FieldLabel>
            <Input v-model="email" type="email" placeholder="you@example.com" required class="h-11" />
          </Field>

          <div v-if="error" class="text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2 text-center">
            {{ error }}
          </div>

          <Button type="submit" :disabled="loading" class="w-full h-11 mt-1 text-[15px] font-medium">
            <Loader2 v-if="loading" class="mr-2 h-4 w-4 animate-spin" />
            Send reset link
          </Button>

          <button
            type="button"
            class="flex items-center justify-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
            @click="router.push('/login')"
          >
            <ArrowLeft class="size-3.5" />
            Back to login
          </button>
        </form>
      </div>
    </div>
  </div>
</template>
