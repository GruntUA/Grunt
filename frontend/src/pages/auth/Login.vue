<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Fingerprint, Mail } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import { useSiteConfig } from '@/core/composables/useSiteConfig'
import { authApi, type AuthMethod } from '@/core/api/auth'
import { isWebAuthnSupported } from '@/core/composables/useWebAuthn'
import AppBrand from '@/components/app/AppBrand.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
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
    // Providers endpoint unavailable — password login still works.
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
          <button
            type="button"
            class="text-primary hover:underline font-medium mt-2"
            @click="signupDone = false; switchMode('signin')"
          >
            {{ t('Back to sign in') }}
          </button>
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
            <div class="flex flex-col gap-1.5">
              <label for="email-code" class="font-medium">{{ t('Code from the email') }}</label>
              <Input
                id="email-code"
                v-model="emailCode"
                inputmode="numeric"
                autocomplete="one-time-code"
                placeholder="000000"
                required
                class="w-full tracking-[0.3em] text-center"
              />
            </div>

            <p v-if="notice" class="text-foreground bg-muted rounded-lg px-3 py-2 text-center border border-border">
              {{ notice }}
            </p>
            <p v-if="error" class="text-destructive bg-destructive/10 rounded-lg px-3 py-2 text-center border border-destructive/20">
              {{ error }}
            </p>

            <div class="flex flex-col gap-3">
              <Button type="submit" :disabled="emailVerifying" class="w-full">
                <Spinner v-if="emailVerifying" class="size-4 mr-2" />
                {{ t('Confirm') }}
              </Button>
              <div class="flex items-center justify-between text-muted-foreground">
                <button type="button" class="hover:underline" :disabled="emailSending" @click="startEmailLogin">
                  {{ t('Resend') }}
                </button>
                <button type="button" class="hover:underline" @click="resetEmailLogin">
                  {{ t('Another sign-in method') }}
                </button>
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

            <div v-if="hasAlternatives" class="relative text-center">
              <div class="absolute inset-0 flex items-center" aria-hidden="true">
                <span class="w-full border-t border-border"></span>
              </div>
              <span class="bg-card text-muted-foreground relative px-2">{{ t('or enter your password') }}</span>
            </div>

            <!-- Full name (signup only) -->
            <div v-if="isSignup" class="flex flex-col gap-1.5">
              <label for="full-name" class="font-medium">{{ t('Full name') }}</label>
              <Input id="full-name" v-model="fullName" type="text" autocomplete="name" :placeholder="t('John Smith')" required class="w-full" />
            </div>

            <!-- Email -->
            <div class="flex flex-col gap-1.5">
              <label for="email" class="font-medium">Email</label>
              <Input id="email" v-model="email" type="email" autocomplete="username" placeholder="admin@grunt.local" required class="w-full" />
            </div>

            <!-- Password -->
            <div class="flex flex-col gap-1.5">
              <div class="flex items-center">
                <label for="password" class="font-medium">{{ t('Password') }}</label>
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
                class="w-full"
              />
            </div>

            <!-- Confirm password (signup only) -->
            <div v-if="isSignup" class="flex flex-col gap-1.5">
              <label for="password-confirm" class="font-medium">{{ t('Repeat password') }}</label>
              <Input id="password-confirm" v-model="passwordConfirm" type="password" autocomplete="new-password" placeholder="••••••••" required class="w-full" />
            </div>

            <p v-if="notice" class="text-foreground bg-muted rounded-lg px-3 py-2 text-center border border-border">
              {{ notice }}
            </p>
            <p v-if="error" class="text-destructive bg-destructive/10 rounded-lg px-3 py-2 text-center border border-destructive/20">
              {{ error }}
            </p>

            <div class="flex flex-col gap-3">
              <Button type="submit" :disabled="loading" class="w-full">
                <Spinner v-if="loading" class="size-4 mr-2" />
                {{ submitLabel }}
              </Button>
              <p v-if="isSignup" class="text-center text-muted-foreground">
                {{ t('Already have an account?') }}
                <button type="button" class="text-primary hover:underline font-medium" @click="switchMode('signin')">{{ t('Sign in') }}</button>
              </p>
              <p v-else-if="allowRegistration" class="text-center text-muted-foreground">
                {{ t('No account?') }}
                <button type="button" class="text-primary hover:underline font-medium" @click="switchMode('signup')">{{ t('Sign up') }}</button>
              </p>
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
