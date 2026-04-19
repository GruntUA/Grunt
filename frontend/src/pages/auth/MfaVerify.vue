<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Input } from '@/components/ui/input'
import { Field, FieldLabel } from '@/components/ui/field'
import { Loader2, ShieldCheck, ArrowRight, ArrowLeft } from '@lucide/vue'
import { authApi } from '@/core/api'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/core/composables/useToast'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const toast = useToast()

const code = ref('')
const loading = ref(false)
const error = ref('')

// Get temporary MFA token from URL query
const mfaToken = (route.query.token as string) || ''

async function handleVerify() {
  if (!code.value || code.value.length < 6) return
  error.value = ''
  loading.value = true

  try {
    const data = await authApi.verifyMfaLogin(mfaToken, code.value)

    // Complete login in store
    authStore.token = data.access_token
    authStore.refreshToken = data.refresh_token
    authStore.user = data.user
    localStorage.setItem('grunt_token', data.access_token)
    localStorage.setItem('grunt_refresh_token', data.refresh_token)

    toast.success('Вітаємо в системі!')
    setTimeout(() => {
      router.push('/')
    }, 200)
  } catch (e: any) {
    console.error('MFA Verify Error:', e)
    error.value = e?.response?.data?.detail || e?.message || 'Невірний код. Спробуйте ще раз.'
    toast.error(error.value)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div
    class="min-h-screen flex items-center justify-center bg-gradient-to-br from-emerald-50 via-background to-emerald-50/20 relative overflow-hidden p-6">
    <!-- Decorative background -->
    <div class="absolute inset-0 overflow-hidden pointer-events-none">
      <div class="absolute -top-24 -right-24 w-96 h-96 bg-emerald-100/30 rounded-full blur-3xl opacity-50" />
      <div class="absolute -bottom-32 -left-32 w-[500px] h-[500px] bg-emerald-50/50 rounded-full blur-3xl opacity-50" />
    </div>

    <div class="relative w-full max-w-[420px]">
      <div class="text-center mb-10">
        <div
          class="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-primary text-primary-foreground mb-4 shadow-xl shadow-primary/20">
          <ShieldCheck class="w-8 h-8" />
        </div>
        <h1 class="text-2xl font-bold text-foreground tracking-tight">Двофакторна перевірка</h1>
        <p class="text-sm text-muted-foreground mt-2 max-w-[280px] mx-auto leading-relaxed">
          Будь ласка, введіть 6-значний код з вашого додатку або резервний код.
        </p>
      </div>

      <div class="bg-card border border-border/60 shadow-2xl shadow-black/[0.03] rounded-3xl p-8 backdrop-blur-sm">
        <form class="flex flex-col gap-6" @submit.prevent="handleVerify">
          <Field>
            <FieldLabel>Код доступу</FieldLabel>
            <Input v-model="code" type="text" inputmode="numeric" autocomplete="one-time-code"
              placeholder="000 000" maxlength="8" required autofocus
              class="h-16 text-center text-3xl font-mono tracking-[0.3em] border-2 focus-visible:ring-primary/20 bg-background/50" />
          </Field>

          <div v-if="error"
            class="text-xs text-destructive bg-destructive/5 border border-destructive/10 rounded-xl px-4 py-3 text-center font-medium animate-in fade-in zoom-in duration-200">
            {{ error }}
          </div>

          <Button type="submit" :disabled="loading || code.length < 6"
            class="w-full h-14 text-lg font-bold shadow-lg shadow-primary/20 active:scale-[0.98] transition-transform">
            <Loader2 v-if="loading" class="mr-2 h-5 w-5 animate-spin" />
            <span v-else>Підтвердити вхід</span>
            <ArrowRight v-if="!loading" class="ml-2 h-5 w-5" />
          </Button>

          <Button text type="button" class="h-10 text-muted-foreground hover:text-foreground text-xs"
            @click="router.push('/login')">
            <ArrowLeft class="mr-2 h-3 w-3" />
            Повернутися до входу
          </Button>
        </form>
      </div>

      <p class="text-center text-[10px] text-muted-foreground/40 mt-10 uppercase tracking-[0.2em] font-bold">
        Grunt Security Engine
      </p>
    </div>
  </div>
</template>
