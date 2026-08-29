<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useSiteConfig } from '@/core/composables/useSiteConfig'
import AppBrand from '@/components/app/AppBrand.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Spinner } from '@/components/ui/spinner'

const router = useRouter()
const auth = useAuthStore()
const { allowRegistration } = useSiteConfig()

const email = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    const res = await auth.login(email.value, password.value)
    if (res.mfa_required) {
      router.push({
        name: 'mfa-verify',
        query: {
          token: res.mfa_token,
          expected: res.expected_code
        }
      })
    } else {
      router.push({ name: 'desk' })
    }
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
  <div class="bg-muted flex min-h-svh flex-col items-center justify-center gap-6 p-6 md:p-10">
    <div class="flex w-full max-w-sm flex-col gap-6">
      <!-- Logo -->
      <AppBrand class="self-center" />


      <!-- Card -->
      <Card>
        <div class="flex flex-col items-center gap-1.5 px-6 text-center">
          <h3 class="font-semibold text-xl">З поверненням</h3>
          <p class="text-muted-foreground">Увійдіть у свій акаунт</p>
        </div>
        <div class="px-6">
          <form @submit.prevent="handleLogin" class="flex flex-col gap-5">
            <!-- OAuth Google (shown only when configured) -->
            <div id="oauth-providers" class="hidden [.oauth-enabled_&]:flex">
              <a
                href="/api/v1/oauth/google/authorize"
                class="flex items-center justify-center gap-2 w-full h-10 rounded-md border border-border bg-background hover:bg-muted/50 transition-colors font-medium"
              >
                <svg class="size-4" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                  <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
                  <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                  <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                  <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
                </svg>
                Увійти через Google
              </a>
            </div>

            <div class="[.oauth-enabled_&]:flex items-center gap-4 hidden">
                <Separator />
                <span class="text-xs text-muted-foreground whitespace-nowrap">або продовжити з</span>
                <Separator />
            </div>

            <!-- Email -->
            <div class="flex flex-col gap-1.5">
              <label for="email" class="font-medium">Email</label>
              <Input id="email" v-model="email" type="email" autocomplete="username" placeholder="admin@grunt.local" required class="w-full" />
            </div>

            <!-- Password -->
            <div class="flex flex-col gap-1.5">
              <div class="flex items-center">
                <label for="password" class="font-medium">Пароль</label>
                <router-link
                  to="/forgot-password"
                  class="ml-auto underline-offset-4 hover:underline text-muted-foreground"
                >
                  Забули пароль?
                </router-link>
              </div>
              <Input id="password" v-model="password" type="password" autocomplete="current-password" placeholder="••••••••" required class="w-full" />
            </div>

            <!-- Error -->
            <p v-if="error" class="text-destructive bg-destructive/10 rounded-lg px-3 py-2 text-center border border-destructive/20">
              {{ error }}
            </p>

            <!-- Submit -->
            <div class="flex flex-col gap-3">
              <Button type="submit" :disabled="loading" class="w-full">
                <Spinner v-if="loading" class="size-4 mr-2" />
                Увійти
              </Button>
              <p v-if="allowRegistration" class="text-center text-muted-foreground">
                Немає акаунту?
                <router-link to="/register" class="text-primary hover:underline font-medium">Зареєструватись</router-link>
              </p>
            </div>
          </form>
        </div>
      </Card>

      <p class="px-6 text-center text-xs text-muted-foreground leading-relaxed">
        Натискаючи «Увійти», ви погоджуєтесь з нашими
        <a href="#" class="underline underline-offset-2 hover:text-foreground">Умовами використання</a> та <a href="#" class="underline underline-offset-2 hover:text-foreground">Політикою конфіденційності</a>.
      </p>
    </div>
  </div>
</template>
