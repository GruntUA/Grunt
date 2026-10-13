<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { REGEXP_ONLY_DIGITS } from 'vue-input-otp'
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Fingerprint, Mail } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import { useSiteConfig } from '@/core/composables/useSiteConfig'
import { authApi, type AuthMethod } from '@/core/api/auth'
import { isWebAuthnSupported } from '@/core/composables/useWebAuthn'
import AppBrand from '@/components/app/AppBrand.vue'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Field, FieldDescription, FieldLabel, FieldSeparator } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { InputOTP, InputOTPGroup, InputOTPSeparator, InputOTPSlot } from '@/components/ui/input-otp'
import { Spinner } from '@/components/ui/spinner'

const { t } = useI18n()

type Mode = 'signin' | 'signup'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const { allowRegistration } = useSiteConfig()

const PENDING_MSG =
  t('Your account is registered and awaiting administrator approval. Try signing in later.')

const mode = ref<Mode>(route.path === '/signup' ? 'signup' : 'signin')
watch(
  () => route.path,
  (p) => { mode.value = p === '/signup' ? 'signup' : 'signin' },
)

const fullName = ref('')
const email = ref('')
const password = ref('')
const passwordConfirm = ref('')
const loading = ref(false)
const passkeyLoading = ref(false)
const error = ref('')
const notice = ref('')
const signupDone = ref(false)

// "Sign in with email" (passwordless code / magic link)
const emailStage = ref<'idle' | 'code'>('idle')
const emailTarget = ref('')
const emailChallengeToken = ref('')
const emailCode = ref('')
const emailSending = ref(false)
const emailVerifying = ref(false)

const isSignup = computed(() => mode.value === 'signup')
const title = computed(() => (isSignup.value ? t('Create an account') : t('Welcome back')))
const subtitle = computed(() =>
  isSignup.value ? t('Fill in the form to sign up') : t('Sign in to your account'),
)
const submitLabel = computed(() => (isSignup.value ? t('Sign up') : t('Sign in')))

const methods = ref<AuthMethod[]>([])
const redirectMethods = computed(() => methods.value.filter((m) => m.kind === 'redirect'))
const hasPasskey = computed(
  () => isWebAuthnSupported() && methods.value.some((m) => m.name === 'webauthn'),
)
const hasEmailLogin = computed(() => methods.value.some((m) => m.name === 'email'))
const hasAlternatives = computed(
  () => hasPasskey.value || hasEmailLogin.value || redirectMethods.value.length > 0,
)

onMounted(async () => {
  if (mode.value === 'signup' && !allowRegistration.value) router.replace('/login')
  await consumeExternalRedirect()
  try {
    methods.value = await authApi.listMethods()
  } catch {
    // Providers endpoint unavailable - password login still works.
  }
})

function switchMode(next: Mode) {
  error.value = ''
  notice.value = ''
  router.replace(next === 'signup' ? '/signup' : '/login')
}

/** Pick up tokens the OAuth callback left in the URL fragment. */
async function consumeExternalRedirect() {
  const hash = window.location.hash?.slice(1)
  if (!hash) return
  const p = new URLSearchParams(hash)
  const known = ['access_token', 'error', 'mfa_required', 'email_login_token']
  if (!known.some((k) => p.has(k))) return
  history.replaceState(null, '', window.location.pathname + window.location.search)

  // Magic link from the "sign in with email" mail.
  if (p.has('email_login_token')) {
    try {
      const res = await auth.completeEmailLogin({ token: p.get('email_login_token')! })
      if (res.approval_pending) notice.value = PENDING_MSG
      else if (res.mfa_required) router.push({ name: 'mfa-verify', query: { token: res.mfa_token } })
      else router.push({ name: 'desk' })
    } catch (e: any) {
      error.value =
        e?.response?.data?.error?.message || t('The sign-in link is invalid or expired')
    }
    return
  }

  if (p.get('approval_pending')) {
    notice.value = PENDING_MSG
    return
  }
  if (p.get('error')) {
    error.value = t('Could not sign in with the external provider')
    return
  }
  if (p.get('mfa_required')) {
    router.push({ name: 'mfa-verify', query: { token: p.get('mfa_token') } })
    return
  }
  const at = p.get('access_token')
  const rt = p.get('refresh_token')
  if (at && rt) {
    await auth.setSession(at, rt)
    router.push({ name: 'desk' })
  }
}

function toMfa(res: { mfa_token?: string; expected_code?: string }) {
  router.push({
    name: 'mfa-verify',
    query: { token: res.mfa_token, expected: res.expected_code },
  })
}

async function handleSubmit() {
  error.value = ''
  notice.value = ''

  if (isSignup.value) {
    if (password.value !== passwordConfirm.value) {
      error.value = t('Passwords do not match')
      return
    }
    if (password.value.length < 8) {
      error.value = t('Password must be at least 8 characters')
      return
    }
  }

  loading.value = true
  try {
    if (isSignup.value) {
      const { approval_pending } = await authApi.register(
        email.value,
        password.value,
        fullName.value,
      )
      if (approval_pending) {
        signupDone.value = true
        return
      }
    }
    const res = await auth.login(email.value, password.value)
    if (res.approval_pending) notice.value = PENDING_MSG
    else if (res.mfa_required) toMfa(res)
    else router.push({ name: 'desk' })
  } catch (e: any) {
    const status = e?.response?.status
    if (status === 409) {
      error.value = t('A user with this email already exists')
    } else if (status === 401 && !isSignup.value) {
      error.value = t('Invalid email or password')
    } else if (status === 429) {
      error.value = e?.response?.data?.detail || t('Too many failed attempts. The account is temporarily locked.')
    } else {
      error.value = e?.response?.data?.error?.message || e?.message || t('Error')
    }
  } finally {
    loading.value = false
  }
}

async function loginWithPasskey() {
  error.value = ''
  notice.value = ''
  passkeyLoading.value = true
  try {
    await auth.loginWithPasskey(email.value || undefined)
    router.push({ name: 'desk' })
  } catch (e: any) {
    if (e?.message === 'approval_pending') {
      notice.value = PENDING_MSG
      return
    }
    if (e?.message === 'mfa_required' && e.mfa) {
      toMfa({ mfa_token: e.mfa.mfa_token })
      return
    }
    if (e?.name === 'NotAllowedError') return // user dismissed the prompt
    error.value = e?.response?.data?.error?.message || e?.message || t('Could not sign in with the passkey')
  } finally {
    passkeyLoading.value = false
  }
}

async function loginWithRedirect(provider: string) {
  error.value = ''
  try {
    const { redirect_url } = await authApi.begin(provider)
    window.location.assign(redirect_url)
  } catch (e: any) {
    error.value = e?.response?.data?.error?.message || e?.message || t('Provider unavailable')
  }
}

async function startEmailLogin() {
  error.value = ''
  notice.value = ''
  const target = email.value.trim()
  if (!target) {
    error.value = t('Enter your email address first')
    return
  }
  emailSending.value = true
  try {
    const { challenge_token } = await auth.beginEmailLogin(target)
    emailChallengeToken.value = challenge_token
    emailTarget.value = target
    emailCode.value = ''
    emailStage.value = 'code'
  } catch (e: any) {
    error.value =
      e?.response?.data?.error?.message || e?.message || t('Could not send the code')
  } finally {
    emailSending.value = false
  }
}

function resetEmailLogin() {
  emailStage.value = 'idle'
  emailChallengeToken.value = ''
  emailCode.value = ''
  error.value = ''
  notice.value = ''
}

async function verifyEmailCode() {
  if (emailVerifying.value) return
  error.value = ''
  if (emailCode.value.trim().length < 4) {
    error.value = t('Enter the code from the email')
    return
  }
  emailVerifying.value = true
  try {
    const res = await auth.completeEmailLogin({
      challenge_token: emailChallengeToken.value,
      code: emailCode.value.trim(),
    })
    if (res.approval_pending) {
      notice.value = PENDING_MSG
      resetEmailLogin()
    } else if (res.mfa_required) {
      toMfa({ mfa_token: res.mfa_token })
    } else {
      router.push({ name: 'desk' })
    }
  } catch (e: any) {
    error.value =
      e?.response?.data?.error?.message || e?.message || t('Invalid or expired code')
  } finally {
    emailVerifying.value = false
  }
}
</script>

<template>
  <div class="bg-muted flex min-h-svh flex-col items-center justify-center gap-6 p-6 md:p-10">
    <div class="flex w-full max-w-sm flex-col gap-6">
      <AppBrand class="self-center" />

      <!-- Registration submitted, awaiting approval -->
      <Card v-if="signupDone">
        <div class="flex flex-col items-center gap-2 px-6 text-center">
          <h3 class="font-semibold text-xl">{{ t('Request sent') }}</h3>
          <p class="text-muted-foreground leading-relaxed">
            {{ t('Your account has been created and is awaiting administrator approval. You can sign in once it is approved.') }}
          </p>
          <Button type="button" variant="link" @click="signupDone = false; switchMode('signin')">
            {{ t('Back to sign in') }}
          </Button>
        </div>
      </Card>

      <Card v-else>
        <div class="flex flex-col items-center gap-1.5 px-6 text-center">
          <h3 class="font-semibold text-xl">{{ title }}</h3>
          <p class="text-muted-foreground">{{ subtitle }}</p>
        </div>
        <div class="px-6">
          <!-- Passwordless email: enter the code from the mail -->
          <form
            v-if="emailStage === 'code'"
            @submit.prevent="verifyEmailCode"
            class="flex flex-col gap-5"
          >
            <p class="text-muted-foreground text-center leading-relaxed">
              {{ t('We sent a sign-in code and link to') }}
              <span class="text-foreground font-medium">{{ emailTarget }}</span>.
              {{ t('Enter the code or follow the link in the email.') }}
            </p>
            <Field class="items-center">
              <FieldLabel for="email-code">{{ t('Code from the email') }}</FieldLabel>
              <InputOTP
                id="email-code"
                v-model="emailCode"
                :maxlength="6"
                :pattern="REGEXP_ONLY_DIGITS"
                autocomplete="one-time-code"
                @complete="verifyEmailCode"
              >
                <InputOTPGroup>
                  <InputOTPSlot v-for="i in 3" :key="i" :index="i - 1" />
                </InputOTPGroup>
                <InputOTPSeparator />
                <InputOTPGroup>
                  <InputOTPSlot v-for="i in 3" :key="i" :index="i + 2" />
                </InputOTPGroup>
              </InputOTP>
            </Field>

            <Alert v-if="notice">
              <AlertDescription>{{ notice }}</AlertDescription>
            </Alert>
            <Alert v-if="error" variant="destructive">
              <AlertDescription>{{ error }}</AlertDescription>
            </Alert>

            <div class="flex flex-col gap-3">
              <Button type="submit" :disabled="emailVerifying" class="w-full">
                <Spinner v-if="emailVerifying" />
                {{ t('Confirm') }}
              </Button>
              <div class="flex items-center justify-between">
                <Button type="button" variant="link" size="sm" class="px-0 text-muted-foreground" :disabled="emailSending" @click="startEmailLogin">
                  {{ t('Resend') }}
                </Button>
                <Button type="button" variant="link" size="sm" class="px-0 text-muted-foreground" @click="resetEmailLogin">
                  {{ t('Another sign-in method') }}
                </Button>
              </div>
            </div>
          </form>

          <form v-else @submit.prevent="handleSubmit" class="flex flex-col gap-5">
            <!-- Alternative methods (discovered from /api/v1/auth/methods) -->
            <div v-if="hasAlternatives" class="flex flex-col gap-2.5">
              <Button
                v-if="hasPasskey"
                type="button"
                variant="outline"
                class="w-full"
                :disabled="passkeyLoading"
                @click="loginWithPasskey"
              >
                <Spinner v-if="passkeyLoading" class="size-4 mr-2" />
                <Fingerprint v-else class="size-4 mr-2" />
                {{ t('Passkey') }}
              </Button>
              <Button
                v-for="m in redirectMethods"
                :key="m.name"
                type="button"
                variant="outline"
                class="w-full"
                @click="loginWithRedirect(m.name)"
              >
                {{ t('Continue with {provider}', { provider: m.label }) }}
              </Button>
              <Button
                v-if="hasEmailLogin"
                type="button"
                variant="outline"
                class="w-full"
                :disabled="emailSending"
                @click="startEmailLogin"
              >
                <Spinner v-if="emailSending" class="size-4 mr-2" />
                <Mail v-else class="size-4 mr-2" />
                {{ t('Email me a code') }}
              </Button>
            </div>

            <FieldSeparator v-if="hasAlternatives" class="*:data-[slot=field-separator-content]:bg-card">
              {{ t('or enter your password') }}
            </FieldSeparator>

            <!-- Full name (signup only) -->
            <Field v-if="isSignup">
              <FieldLabel for="full-name">{{ t('Full name') }}</FieldLabel>
              <Input id="full-name" v-model="fullName" type="text" autocomplete="name" :placeholder="t('John Smith')" required />
            </Field>

            <!-- Email -->
            <Field>
              <FieldLabel for="email">Email</FieldLabel>
              <Input id="email" v-model="email" type="email" autocomplete="username" placeholder="admin@grunt.local" required />
            </Field>

            <!-- Password -->
            <Field>
              <div class="flex items-center">
                <FieldLabel for="password">{{ t('Password') }}</FieldLabel>
                <router-link
                  v-if="!isSignup"
                  to="/forgot-password"
                  class="ml-auto underline-offset-4 hover:underline text-muted-foreground"
                >
                  {{ t('Forgot password?') }}
                </router-link>
              </div>
              <Input
                id="password"
                v-model="password"
                type="password"
                :autocomplete="isSignup ? 'new-password' : 'current-password'"
                :placeholder="isSignup ? t('At least 8 characters') : '••••••••'"
                required
              />
            </Field>

            <!-- Confirm password (signup only) -->
            <Field v-if="isSignup">
              <FieldLabel for="password-confirm">{{ t('Repeat password') }}</FieldLabel>
              <Input id="password-confirm" v-model="passwordConfirm" type="password" autocomplete="new-password" placeholder="••••••••" required />
            </Field>

            <Alert v-if="notice">
              <AlertDescription>{{ notice }}</AlertDescription>
            </Alert>
            <Alert v-if="error" variant="destructive">
              <AlertDescription>{{ error }}</AlertDescription>
            </Alert>

            <div class="flex flex-col gap-3">
              <Button type="submit" :disabled="loading" class="w-full">
                <Spinner v-if="loading" />
                {{ submitLabel }}
              </Button>
              <FieldDescription v-if="isSignup" class="text-center">
                {{ t('Already have an account?') }}
                <Button type="button" variant="link" class="h-auto p-0" @click="switchMode('signin')">{{ t('Sign in') }}</Button>
              </FieldDescription>
              <FieldDescription v-else-if="allowRegistration" class="text-center">
                {{ t('No account?') }}
                <Button type="button" variant="link" class="h-auto p-0" @click="switchMode('signup')">{{ t('Sign up') }}</Button>
              </FieldDescription>
            </div>
          </form>
        </div>
      </Card>

      <p class="px-6 text-center text-muted-foreground leading-relaxed">
        {{ t('By continuing, you agree to our') }}
        <a href="#" class="underline underline-offset-2 hover:text-foreground">{{ t('Terms of Service') }}</a> {{ t('and') }} <a href="#" class="underline underline-offset-2 hover:text-foreground">{{ t('Privacy Policy') }}</a>.
      </p>
    </div>
  </div>
</template>
