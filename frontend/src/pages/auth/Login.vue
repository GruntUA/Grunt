<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { FormField } from '@/components/ui/form-field'
import { Loader2, Sprout } from 'lucide-vue-next'

const router = useRouter()
const auth = useAuthStore()

const email = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    const { mfa_required } = await auth.login(email.value, password.value)
    router.push(mfa_required ? '/mfa-verify' : '/')
  } catch (e: any) {
    const status = e?.response?.status
    if (status === 401) {
      error.value = 'Невірний email або пароль'
    } else if (status === 429) {
      error.value = e?.response?.data?.detail || 'Забагато невдалих спроб. Акаунт тимчасово заблоковано.'
    } else {
      error.value = e?.response?.data?.error?.message || e?.message || 'Помилка входу'
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gradient-to-br from-emerald-50 via-background to-emerald-50/30 relative overflow-hidden">
    <!-- Decorative background elements -->
    <div class="absolute inset-0 overflow-hidden pointer-events-none">
      <div class="absolute -top-24 -right-24 w-96 h-96 bg-emerald-100/40 rounded-full blur-3xl" />
      <div class="absolute -bottom-32 -left-32 w-[500px] h-[500px] bg-emerald-50/60 rounded-full blur-3xl" />
    </div>

    <div class="relative w-full max-w-[420px] mx-4">
      <!-- Logo & branding -->
      <div class="text-center mb-8">
        <div class="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-primary text-primary-foreground mb-4 shadow-lg shadow-primary/20">
          <Sprout class="w-7 h-7" />
        </div>
        <h1 class="text-2xl font-bold text-foreground tracking-tight">Ґрунт</h1>
        <p class="text-sm text-muted-foreground mt-1">Увійдіть у свій акаунт</p>
      </div>

      <!-- Login card -->
      <div class="bg-card rounded-xl shadow-xl shadow-black/[0.04] border border-border/60 p-8">
        <form class="flex flex-col gap-5" @submit.prevent="handleLogin">
          <FormField label="Email" required>
            <template #default="{ id }">
              <Input
                :id="id"
                v-model="email"
                type="email"
                placeholder="admin@grunt.local"
                required
                class="h-11"
              />
            </template>
          </FormField>

          <div class="flex flex-col gap-1.5">
            <div class="flex items-center justify-between">
              <label class="text-sm font-medium text-foreground">Пароль <span class="text-destructive">*</span></label>
              <router-link to="/forgot-password" class="text-xs text-muted-foreground hover:text-foreground transition-colors">
                Забули пароль?
              </router-link>
            </div>
            <Input
              v-model="password"
              type="password"
              placeholder="••••••••"
              required
              class="h-11"
            />
          </div>

          <div v-if="error" class="text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2 text-center">
            {{ error }}
          </div>

          <Button type="submit" :disabled="loading" class="w-full h-11 mt-1 text-[15px] font-medium">
            <Loader2 v-if="loading" class="mr-2 h-4 w-4 animate-spin" />
            Увійти
          </Button>
        </form>

        <!-- OAuth providers (shown only when configured via feature flags) -->
        <div id="oauth-providers" class="mt-4 space-y-2 hidden [.oauth-enabled_&]:block">
          <div class="relative flex items-center py-1">
            <div class="flex-grow border-t border-border" />
            <span class="mx-3 text-xs text-muted-foreground">або</span>
            <div class="flex-grow border-t border-border" />
          </div>
          <a
            href="/api/v1/oauth/google/authorize"
            class="flex items-center justify-center gap-2 w-full h-10 rounded-md border border-border bg-background hover:bg-muted/50 transition-colors text-sm font-medium"
          >
            <!-- Google icon SVG -->
            <svg class="size-4" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
            </svg>
            Увійти через Google
          </a>
        </div>
      </div>

      <p class="text-center text-xs text-muted-foreground/60 mt-6">
        Працює на базі Ґрунт Framework
      </p>
    </div>
  </div>
</template>
