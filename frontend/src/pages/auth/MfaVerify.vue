<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ShieldCheck, ArrowRight, ArrowLeft, Copy } from '@lucide/vue'
import { authApi } from '@/core/api'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/core/composables/useToast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'

const { t } = useI18n()

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
// token: enroll (QR -> code -> backup codes) instead of verifying.
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
    error.value = e?.response?.data?.detail || e?.message || t('Could not start 2FA setup.')
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
    error.value = e?.response?.data?.detail || e?.message || t('Invalid code. Try again.')
  } finally {
    loading.value = false
  }
}

async function copyBackupCodes() {
  await navigator.clipboard.writeText(backupCodes.value.join('\n'))
  toast.success(t('Backup codes copied'))
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

    toast.success(t('Welcome!'))
    setTimeout(() => {
      router.push({ name: 'desk' })
    }, 200)
  } catch (e: any) {
    console.error('MFA Verify Error:', e)
    error.value = e?.response?.data?.detail || e?.message || t('Invalid code. Try again.')
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
          {{ isSetup ? t('2FA setup') : t('Two-factor verification') }}
        </h1>
        <p v-if="isSetup" class="text-muted-foreground mt-2 max-w-[320px] mx-auto leading-relaxed">
          {{ t('Your role requires two-factor authentication. Scan the QR code in your authenticator app and enter the 6-digit code.') }}
        </p>
        <p v-else class="text-muted-foreground mt-2 max-w-[280px] mx-auto leading-relaxed">
          {{ t('Please enter the 6-digit code from your app or a backup code.') }}
        </p>
      </div>

      <div v-if="backupCodes.length" class="bg-card border border-border shadow-sm rounded-lg p-8 flex flex-col gap-6">
        <div class="flex flex-col gap-2">
          <p class="font-semibold">{{ t('2FA is on. Save your backup codes') }}</p>
          <p class="text-muted-foreground">
            {{ t('Each code can be used once if you lose access to your authenticator. They will not be shown again.') }}
          </p>
        </div>
        <ul class="grid grid-cols-2 gap-2 font-mono text-sm text-center">
          <li v-for="c in backupCodes" :key="c" class="rounded-md bg-muted py-1.5">{{ c }}</li>
        </ul>
        <Button variant="outline" type="button" @click="copyBackupCodes">
          <Copy class="mr-2 h-4 w-4" />
          {{ t('Copy codes') }}
        </Button>
        <Button type="button" class="w-full h-12" @click="router.push({ name: 'desk' })">
          {{ t('Continue') }}
          <ArrowRight class="ml-2 h-5 w-5" />
        </Button>
      </div>

      <div v-else class="bg-card border border-border shadow-sm rounded-lg p-8">
        <div v-if="isSetup && setupInfo" class="flex flex-col items-center gap-3 mb-6">
          <div class="rounded-md bg-white p-2 [&>svg]:size-44" v-html="setupInfo.qr_svg" />
          <p class="text-muted-foreground text-center">
            {{ t('Or enter the key manually:') }}
            <span class="block font-mono text-foreground break-all select-all">{{ setupInfo.secret }}</span>
          </p>
        </div>
        <form class="flex flex-col gap-6" @submit.prevent="isSetup ? handleEnroll() : handleVerify()">
          <div class="flex flex-col gap-2 text-center">
            <label class="font-semibold text-muted-foreground uppercase tracking-widest">{{ t('Access code') }}</label>
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
            <span>{{ isSetup ? t('Enable 2FA and sign in') : t('Confirm sign-in') }}</span>
            <Spinner v-if="loading" class="ml-2 h-5 w-5 order-last" />
            <ArrowRight v-else class="ml-2 h-5 w-5 order-last" />
          </Button>

          <Button variant="ghost" type="button" class="h-10 text-muted-foreground hover:text-foreground text-xs" @click="router.push('/login')">
            <ArrowLeft class="mr-2 h-3 w-3" />
            {{ t('Back to sign in') }}
          </Button>
        </form>
      </div>

      <p class="text-center text-muted-foreground/40 mt-10 uppercase tracking-[0.2em] font-semibold">
        Grunt Security Engine
      </p>
    </div>
  </div>
</template>
