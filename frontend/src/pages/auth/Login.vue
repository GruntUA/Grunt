<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Fingerprint, Smartphone } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import { useSiteConfig } from '@/core/composables/useSiteConfig'
import { authApi, type AuthMethod } from '@/core/api/auth'
import { isWebAuthnSupported } from '@/core/composables/useWebAuthn'
import AppBrand from '@/components/app/AppBrand.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'

type Mode = 'signin' | 'signup'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const { allowRegistration } = useSiteConfig()

const PENDING_MSG =
  'Ваш акаунт зареєстровано та очікує підтвердження адміністратора. Спробуйте увійти пізніше.'

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
const phoneLoading = ref(false)
const error = ref('')
const notice = ref('')
const signupDone = ref(false)

const isSignup = computed(() => mode.value === 'signup')
const title = computed(() => (isSignup.value ? 'Створити акаунт' : 'З поверненням'))
const subtitle = computed(() =>
  isSignup.value ? 'Заповніть форму для реєстрації' : 'Увійдіть у свій акаунт',
)
const submitLabel = computed(() => (isSignup.value ? 'Зареєструватись' : 'Увійти'))

const methods = ref<AuthMethod[]>([])
const redirectMethods = computed(() => methods.value.filter((m) => m.kind === 'redirect'))
const hasPasskey = computed(
  () => isWebAuthnSupported() && methods.value.some((m) => m.name === 'webauthn'),
)
const hasAlternatives = computed(() => hasPasskey.value || redirectMethods.value.length > 0)

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
  if (!p.has('access_token') && !p.has('error') && !p.has('mfa_required')) return
  history.replaceState(null, '', window.location.pathname + window.location.search)

  if (p.get('approval_pending')) {
    notice.value = PENDING_MSG
    return
  }
  if (p.get('error')) {
    error.value = 'Не вдалося увійти через зовнішній провайдер'
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
      error.value = 'Паролі не співпадають'
      return
    }
    if (password.value.length < 8) {
      error.value = 'Пароль має бути не менше 8 символів'
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
      error.value = 'Користувач з таким email вже існує'
    } else if (status === 401 && !isSignup.value) {
      error.value = 'Невірний email або пароль'
    } else if (status === 429) {
      error.value = e?.response?.data?.detail || 'Забагато невдалих спроб. Акаунт тимчасово заблоковано.'
    } else {
      error.value = e?.response?.data?.error?.message || e?.message || 'Помилка'
    }
  } finally {
    loading.value = false
  }
}

async function runPasskey(
  busy: typeof passkeyLoading,
  opts?: { mode?: 'cross-device' },
) {
  error.value = ''
  notice.value = ''
  busy.value = true
  try {
    await auth.loginWithPasskey(email.value || undefined, opts)
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
    error.value = e?.response?.data?.error?.message || e?.message || 'Не вдалося увійти за ключем доступу'
  } finally {
    busy.value = false
  }
}

const loginWithPasskey = () => runPasskey(passkeyLoading)
const loginFromPhone = () => runPasskey(phoneLoading, { mode: 'cross-device' })

async function loginWithRedirect(provider: string) {
  error.value = ''
  try {
    const { redirect_url } = await authApi.begin(provider)
    window.location.assign(redirect_url)
  } catch (e: any) {
    error.value = e?.response?.data?.error?.message || e?.message || 'Провайдер недоступний'
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
          <h3 class="font-semibold text-xl">Заявку надіслано</h3>
          <p class="text-muted-foreground leading-relaxed">
            Ваш акаунт створено та очікує підтвердження адміністратора.
            Ви зможете увійти після підтвердження.
          </p>
          <button
            type="button"
            class="text-primary hover:underline font-medium mt-2"
            @click="signupDone = false; switchMode('signin')"
          >
            Повернутися до входу
          </button>
        </div>
      </Card>

      <Card v-else>
        <div class="flex flex-col items-center gap-1.5 px-6 text-center">
          <h3 class="font-semibold text-xl">{{ title }}</h3>
          <p class="text-muted-foreground">{{ subtitle }}</p>
        </div>
        <div class="px-6">
          <form @submit.prevent="handleSubmit" class="flex flex-col gap-5">
            <!-- Alternative methods (discovered from /api/v1/auth/methods) -->
            <div v-if="hasAlternatives" class="flex flex-col gap-2.5">
              <Button
                v-if="hasPasskey"
                type="button"
                variant="outline"
                class="w-full"
                :disabled="passkeyLoading || phoneLoading"
                @click="loginWithPasskey"
              >
                <Spinner v-if="passkeyLoading" class="size-4 mr-2" />
                <Fingerprint v-else class="size-4 mr-2" />
                Ключ доступу
              </Button>
              <Button
                v-if="hasPasskey"
                type="button"
                variant="outline"
                class="w-full"
                :disabled="passkeyLoading || phoneLoading"
                @click="loginFromPhone"
              >
                <Spinner v-if="phoneLoading" class="size-4 mr-2" />
                <Smartphone v-else class="size-4 mr-2" />
                Продовжити з телефона
              </Button>
              <Button
                v-for="m in redirectMethods"
                :key="m.name"
                type="button"
                variant="outline"
                class="w-full"
                @click="loginWithRedirect(m.name)"
              >
                Продовжити з {{ m.label }}
              </Button>
            </div>

            <div v-if="hasAlternatives" class="relative text-center">
              <div class="absolute inset-0 flex items-center" aria-hidden="true">
                <span class="w-full border-t border-border"></span>
              </div>
              <span class="bg-card text-muted-foreground relative px-2 text-xs">або через email</span>
            </div>

            <!-- Full name (signup only) -->
            <div v-if="isSignup" class="flex flex-col gap-1.5">
              <label for="full-name" class="font-medium">Повне ім'я</label>
              <Input id="full-name" v-model="fullName" type="text" autocomplete="name" placeholder="Іваненко Іван Іванович" required class="w-full" />
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
                  v-if="!isSignup"
                  to="/forgot-password"
                  class="ml-auto underline-offset-4 hover:underline text-muted-foreground"
                >
                  Забули пароль?
                </router-link>
              </div>
              <Input
                id="password"
                v-model="password"
                type="password"
                :autocomplete="isSignup ? 'new-password' : 'current-password'"
                :placeholder="isSignup ? 'Мінімум 8 символів' : '••••••••'"
                required
                class="w-full"
              />
            </div>

            <!-- Confirm password (signup only) -->
            <div v-if="isSignup" class="flex flex-col gap-1.5">
              <label for="password-confirm" class="font-medium">Повторіть пароль</label>
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
                Вже маєте акаунт?
                <button type="button" class="text-primary hover:underline font-medium" @click="switchMode('signin')">Увійти</button>
              </p>
              <p v-else-if="allowRegistration" class="text-center text-muted-foreground">
                Немає акаунту?
                <button type="button" class="text-primary hover:underline font-medium" @click="switchMode('signup')">Зареєструватись</button>
              </p>
            </div>
          </form>
        </div>
      </Card>

      <p class="px-6 text-center text-xs text-muted-foreground leading-relaxed">
        Продовжуючи, ви погоджуєтесь з нашими
        <a href="#" class="underline underline-offset-2 hover:text-foreground">Умовами використання</a> та <a href="#" class="underline underline-offset-2 hover:text-foreground">Політикою конфіденційності</a>.
      </p>
    </div>
  </div>
</template>
