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
    await auth.login(email.value, password.value)
    router.push('/')
  } catch (e: any) {
    console.error('LOGIN ERROR:', e, e?.response?.status, e?.response?.data)
    error.value = e?.response?.data?.detail || e?.message || 'Невірний email або пароль'
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

          <FormField label="Пароль" required>
            <template #default="{ id }">
              <Input
                :id="id"
                v-model="password"
                type="password"
                placeholder="••••••••"
                required
                class="h-11"
              />
            </template>
          </FormField>

          <div v-if="error" class="text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2 text-center">
            {{ error }}
          </div>

          <Button type="submit" :disabled="loading" class="w-full h-11 mt-1 text-[15px] font-medium">
            <Loader2 v-if="loading" class="mr-2 h-4 w-4 animate-spin" />
            Увійти
          </Button>
        </form>
      </div>

      <p class="text-center text-xs text-muted-foreground/60 mt-6">
        Працює на базі Ґрунт Framework
      </p>
    </div>
  </div>
</template>
