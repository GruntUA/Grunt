<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { REGEXP_ONLY_DIGITS } from 'vue-input-otp'
import { onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ArrowRight, ArrowLeft, Copy } from '@lucide/vue'
import { authApi } from '@/core/api'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/core/composables/useToast'
import AppBrand from '@/components/app/AppBrand.vue'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { InputOTP, InputOTPGroup, InputOTPSeparator, InputOTPSlot } from '@/components/ui/input-otp'
import { Spinner } from '@/components/ui/spinner'
import { afterLoginTarget } from '@/core/loginRedirect'

const { t } = useI18n()

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const toast = useToast()

const code = ref('')
// Verify accepts a 10-character backup code instead of the 6-digit TOTP.
const useBackupCode = ref(false)
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
  if (loading.value || !code.value || code.value.length < 6) return
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
  if (loading.value || !code.value || code.value.length < 6) return
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
      router.push(afterLoginTarget())
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
  <div class="bg-muted flex min-h-svh flex-col items-center justify-center gap-6 p-6 md:p-10">
    <div class="flex w-full max-w-sm flex-col gap-6">
      <AppBrand class="self-center" />

      <Card v-if="backupCodes.length">
        <CardHeader class="text-center">
          <CardTitle class="text-xl">{{ t('2FA is on. Save your backup codes') }}</CardTitle>
          <CardDescription>
            {{ t('Each code can be used once if you lose access to your authenticator. They will not be shown again.') }}
          </CardDescription>
        </CardHeader>
        <CardContent class="flex flex-col gap-4">
          <ul class="grid grid-cols-2 gap-2 font-mono text-sm text-center">
            <li v-for="c in backupCodes" :key="c" class="rounded-md bg-muted py-1.5">{{ c }}</li>
          </ul>
          <Button variant="outline" type="button" @click="copyBackupCodes">
            <Copy />
            {{ t('Copy codes') }}
          </Button>
          <Button type="button" @click="router.push(afterLoginTarget())">
            {{ t('Continue') }}
            <ArrowRight />
          </Button>
        </CardContent>
      </Card>

      <Card v-else>
        <CardHeader class="text-center">
          <CardTitle class="text-xl">{{ isSetup ? t('2FA setup') : t('Two-factor verification') }}</CardTitle>
          <CardDescription>
            {{ isSetup
              ? t('Your role requires two-factor authentication. Scan the QR code in your authenticator app and enter the 6-digit code.')
              : t('Please enter the 6-digit code from your app or a backup code.') }}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div v-if="isSetup && setupInfo" class="flex flex-col items-center gap-3 mb-6">
            <div class="rounded-md bg-white p-2 [&>svg]:size-44" v-html="setupInfo.qr_svg" />
            <p class="text-muted-foreground text-center text-sm">
              {{ t('Or enter the key manually:') }}
              <span class="block font-mono text-foreground break-all select-all">{{ setupInfo.secret }}</span>
            </p>
          </div>
          <form @submit.prevent="isSetup ? handleEnroll() : handleVerify()">
            <FieldGroup>
              <Field class="items-center">
                <FieldLabel :for="useBackupCode ? 'mfa-backup-code' : 'mfa-code'">
                  {{ useBackupCode ? t('Backup code') : t('Access code') }}
                </FieldLabel>
                <Input v-if="useBackupCode" id="mfa-backup-code" v-model="code" autocomplete="off" maxlength="10" required autofocus
                  class="text-center font-mono uppercase" />
                <InputOTP v-else id="mfa-code" v-model="code" :maxlength="6" :pattern="REGEXP_ONLY_DIGITS" autocomplete="one-time-code"
                  autofocus @complete="isSetup ? handleEnroll() : handleVerify()">
                  <InputOTPGroup>
                    <InputOTPSlot v-for="i in 3" :key="i" :index="i - 1" />
                  </InputOTPGroup>
                  <InputOTPSeparator />
                  <InputOTPGroup>
                    <InputOTPSlot v-for="i in 3" :key="i" :index="i + 2" />
                  </InputOTPGroup>
                </InputOTP>
                <Button v-if="!isSetup" variant="link" type="button" size="sm" class="text-muted-foreground"
                  @click="useBackupCode = !useBackupCode; code = ''">
                  {{ useBackupCode ? t('Use the authenticator app code') : t('Use a backup code') }}
                </Button>
              </Field>

              <Alert v-if="error" variant="destructive">
                <AlertDescription>{{ error }}</AlertDescription>
              </Alert>

              <Field>
                <Button type="submit" :disabled="loading || code.length < 6">
                  {{ isSetup ? t('Enable 2FA and sign in') : t('Confirm sign-in') }}
                  <Spinner v-if="loading" />
                  <ArrowRight v-else />
                </Button>
                <Button variant="ghost" type="button" @click="router.push('/login')">
                  <ArrowLeft />
                  {{ t('Back to sign in') }}
                </Button>
              </Field>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
