<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import client from '@/core/api/client'
import { Input } from '@/components/ui/input'
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Loader2, Sprout } from '@lucide/vue'

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
    router.push('/')
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
        Ґрунт
      </a>

      <!-- Card -->
      <div class="bg-card text-card-foreground flex flex-col gap-6 rounded-xl border py-6 shadow-sm">
        <div class="grid auto-rows-min grid-rows-[auto_auto] items-start gap-1.5 px-6 text-center">
          <h3 class="leading-none font-semibold text-xl">Створити акаунт</h3>
          <p class="text-muted-foreground text-sm">Заповніть форму для реєстрації</p>
        </div>
        <div class="px-6">
          <form @submit.prevent="handleRegister">
            <FieldGroup>
              <!-- Full Name -->
              <Field>
                <FieldLabel for="full-name">Повне ім'я</FieldLabel>
                <Input
                  id="full-name"
                  v-model="fullName"
                  type="text"
                  autocomplete="name"
                  placeholder="Іваненко Іван Іванович"
                  required
                />
              </Field>

              <!-- Email -->
              <Field>
                <FieldLabel for="email">Email</FieldLabel>
                <Input
                  id="email"
                  v-model="email"
                  type="email"
                  autocomplete="username"
                  placeholder="user@example.com"
                  required
                />
              </Field>

              <!-- Password -->
              <Field>
                <FieldLabel for="password">Пароль</FieldLabel>
                <Input
                  id="password"
                  v-model="password"
                  type="password"
                  autocomplete="new-password"
                  placeholder="Мінімум 8 символів"
                  required
                />
              </Field>

              <!-- Confirm Password -->
              <Field>
                <FieldLabel for="password-confirm">Повторіть пароль</FieldLabel>
                <Input
                  id="password-confirm"
                  v-model="passwordConfirm"
                  type="password"
                  autocomplete="new-password"
                  placeholder="••••••••"
                  required
                />
              </Field>

              <!-- Error -->
              <p v-if="error" class="text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2 text-center">
                {{ error }}
              </p>

              <!-- Submit -->
              <Field>
                <Button type="submit" :disabled="loading" class="w-full">
                  <Loader2 v-if="loading" class="mr-2 h-4 w-4 animate-spin" />
                  Зареєструватись
                </Button>
                <FieldDescription class="text-center">
                  Вже маєте акаунт?
                  <router-link to="/login">Увійти</router-link>
                </FieldDescription>
              </Field>
            </FieldGroup>
          </form>
        </div>
      </div>
    </div>
  </div>
</template>
