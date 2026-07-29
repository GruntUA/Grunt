<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import client from '@/core/api/client'
import { Sprout } from '@lucide/vue'

const router = useRouter()
const auth = useAuthStore()

const fullName = ref('')
const email = ref('')
const password = ref('')
const passwordConfirm = ref('')
const loading = ref(false)
const error = ref('')

async function handleRegister() {
  error.value = ''

  if (password.value !== passwordConfirm.value) {
    error.value = 'Паролі не співпадають'
    return
  }
  if (password.value.length < 8) {
    error.value = 'Пароль має бути не менше 8 символів'
    return
  }

  loading.value = true
  try {
    await client.post('/api/v1/auth/register', {
      email: email.value,
      password: password.value,
      full_name: fullName.value,
    })
    await auth.login(email.value, password.value)
    router.push({ name: 'desk' })
  } catch (e: any) {
    const status = e?.response?.status
    if (status === 409) {
      error.value = 'Користувач з таким email вже існує'
    } else {
      error.value = e?.response?.data?.error?.message || e?.message || 'Помилка реєстрації'
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
      <a href="#" class="flex items-center gap-2 self-center font-medium">
        <div class="bg-primary text-primary-foreground flex size-6 items-center justify-center rounded-md">
          <Sprout class="size-4" />
        </div>
        <span class="text-foreground">Ґрунт</span>
      </a>

      <!-- Card -->
      <Card>
        <div class="flex flex-col items-center gap-1.5 px-6 text-center">
          <h3 class="font-semibold text-xl">Створити акаунт</h3>
          <p class="text-muted-foreground text-sm">Заповніть форму для реєстрації</p>
        </div>
        <div class="px-6">
          <form @submit.prevent="handleRegister" class="flex flex-col gap-5">
            <!-- Full Name -->
            <div class="flex flex-col gap-1.5">
              <label for="full-name" class="text-sm font-medium">Повне ім'я</label>
              <Input
                id="full-name"
                v-model="fullName"
                type="text"
                autocomplete="name"
                placeholder="Іваненко Іван Іванович"
                required
                class="w-full"
              />
            </div>

            <!-- Email -->
            <div class="flex flex-col gap-1.5">
              <label for="email" class="text-sm font-medium">Email</label>
              <Input
                id="email"
                v-model="email"
                type="email"
                autocomplete="username"
                placeholder="user@example.com"
                required
                class="w-full"
              />
            </div>

            <!-- Password -->
            <div class="flex flex-col gap-1.5">
              <label for="password" class="text-sm font-medium">Пароль</label>
              <Input
                id="password"
                v-model="password"
                type="password"
                autocomplete="new-password"
                placeholder="Мінімум 8 символів"
                required
                class="w-full"
              />
            </div>

            <!-- Confirm Password -->
            <div class="flex flex-col gap-1.5">
              <label for="password-confirm" class="text-sm font-medium">Повторіть пароль</label>
              <Input
                id="password-confirm"
                v-model="passwordConfirm"
                type="password"
                autocomplete="new-password"
                placeholder="••••••••"
                required
                class="w-full"
              />
            </div>

            <!-- Error -->
            <p v-if="error" class="text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2 text-center border border-destructive/20">
              {{ error }}
            </p>

            <!-- Submit -->
            <div class="flex flex-col gap-3">
              <Button type="submit" :disabled="loading" class="w-full">
                <Spinner v-if="loading" class="size-4 mr-2" />
                Зареєструватись
              </Button>
              <p class="text-center text-sm text-muted-foreground">
                Вже маєте акаунт?
                <router-link to="/login" class="text-primary hover:underline font-medium">Увійти</router-link>
              </p>
            </div>
          </form>
        </div>
      </Card>
    </div>
  </div>
</template>
