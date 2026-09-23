<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ShieldCheck, ArrowRight, ArrowLeft, Copy } from '@lucide/vue'
import { authApi } from '@/core/api'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/core/composables/useToast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const toast = useToast()

const code = ref('')
const loading = ref(false)
const error = ref('')

// Get temporary MFA token from URL query
const mfaToken = (route.query.token as string) || ''

// A role that requires 2FA sends users without it here with an `mfa_setup`
// token: enroll (QR → code → backup codes) instead of verifying.
function tokenPurpose(jwt: string): string | null {
  try {
    return JSON.parse(atob(jwt.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).purpose ?? null
  } catch {
    return null
  }
}
const isSetup = tokenPurpose(mfaToken) === 'mfa_setup'
const setupInfo = ref<{ secret: string; qr_svg: string } | null>(null)
const backupCodes = ref<string[]>([])

onMounted(async () => {
  if (!isSetup) return
  try {
    setupInfo.value = await authApi.mfaEnrollBegin(mfaToken)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || 'Не вдалося розпочати налаштування 2FA.'
  }
})

async function handleEnroll() {
  if (!code.value || code.value.length < 6) return
  error.value = ''
  loading.value = true
  try {
    const data = await authApi.mfaEnrollComplete(mfaToken, code.value)
    await authStore.setSession(data.access_token, data.refresh_token)
    backupCodes.value = data.backup_codes || []
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || 'Невірний код. Спробуйте ще раз.'
  } finally {
    loading.value = false
  }
}

async function copyBackupCodes() {
  await navigator.clipboard.writeText(backupCodes.value.join('\n'))
  toast.success('Резервні коди скопійовано')
}

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
      router.push({ name: 'desk' })
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
    class="min-h-screen flex items-center justify-center bg-muted/30 relative overflow-hidden p-6">
    <div class="relative w-full max-w-[420px]">
      <div class="text-center mb-10 flex flex-col items-center">
        <div
          class="inline-flex items-center justify-center w-16 h-16 rounded-lg bg-primary text-primary-foreground mb-4 shadow-sm">
          <ShieldCheck class="w-8 h-8" />
        </div>
        <h1 class="text-2xl font-semibold text-foreground tracking-tight">
          {{ isSetup ? 'Налаштування 2FA' : 'Двофакторна перевірка' }}
        </h1>
        <p v-if="isSetup" class="text-muted-foreground mt-2 max-w-[320px] mx-auto leading-relaxed">
          Ваша роль вимагає двофакторної автентифікації. Відскануйте QR-код у додатку-автентифікаторі
          та введіть 6-значний код.
        </p>
        <p v-else class="text-muted-foreground mt-2 max-w-[280px] mx-auto leading-relaxed">
          Будь ласка, введіть 6-значний код з вашого додатку або резервний код.
        </p>
      </div>

      <div v-if="backupCodes.length" class="bg-card border border-border shadow-sm rounded-lg p-8 flex flex-col gap-6">
        <div class="flex flex-col gap-2">
          <p class="font-semibold">2FA увімкнено. Збережіть резервні коди</p>
          <p class="text-muted-foreground">
            Кожен код можна використати один раз, якщо немає доступу до автентифікатора. Більше вони не показуватимуться.
          </p>
        </div>
        <ul class="grid grid-cols-2 gap-2 font-mono text-sm text-center">
          <li v-for="c in backupCodes" :key="c" class="rounded-md bg-muted py-1.5">{{ c }}</li>
        </ul>
        <Button variant="outline" type="button" @click="copyBackupCodes">
          <Copy class="mr-2 h-4 w-4" />
          Скопіювати коди
        </Button>
        <Button type="button" class="w-full h-12" @click="router.push({ name: 'desk' })">
          Продовжити
          <ArrowRight class="ml-2 h-5 w-5" />
        </Button>
      </div>

      <div v-else class="bg-card border border-border shadow-sm rounded-lg p-8">
        <div v-if="isSetup && setupInfo" class="flex flex-col items-center gap-3 mb-6">
          <div class="rounded-md bg-white p-2 [&>svg]:size-44" v-html="setupInfo.qr_svg" />
          <p class="text-muted-foreground text-center">
            Або введіть ключ вручну:
            <span class="block font-mono text-foreground break-all select-all">{{ setupInfo.secret }}</span>
          </p>
        </div>
        <form class="flex flex-col gap-6" @submit.prevent="isSetup ? handleEnroll() : handleVerify()">
          <div class="flex flex-col gap-2 text-center">
            <label class="font-semibold text-muted-foreground uppercase tracking-widest">Код доступу</label>
            <Input v-model="code" type="text" inputmode="numeric" autocomplete="one-time-code"
              placeholder="000 000" maxlength="8" required autofocus
              class="h-16 text-center text-3xl font-mono tracking-[0.3em] !border-2 focus:!ring-primary/20 bg-background/50" />
          </div>

          <div v-if="error"
            class="text-destructive bg-destructive/5 border border-destructive/10 rounded-lg px-4 py-3 text-center font-medium animate-in fade-in zoom-in duration-200">
            {{ error }}
          </div>

          <Button type="submit" :disabled="loading || code.length < 6"
            class="w-full h-14 text-lg font-semibold shadow-sm">
            <span>{{ isSetup ? 'Увімкнути 2FA та увійти' : 'Підтвердити вхід' }}</span>
            <Spinner v-if="loading" class="ml-2 h-5 w-5 order-last" />
            <ArrowRight v-else class="ml-2 h-5 w-5 order-last" />
          </Button>

          <Button variant="ghost" type="button" class="h-10 text-muted-foreground hover:text-foreground text-xs" @click="router.push('/login')">
            <ArrowLeft class="mr-2 h-3 w-3" />
            Повернутися до входу
          </Button>
        </form>
      </div>

      <p class="text-center text-muted-foreground/40 mt-10 uppercase tracking-[0.2em] font-semibold">
        Grunt Security Engine
      </p>
    </div>
  </div>
</template>
