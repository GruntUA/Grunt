<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { authApi } from '@/core/api/auth-admin'
import { Sprout } from '@lucide/vue'

const router = useRouter()
const route = useRoute()

const token = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const done = ref(false)
const error = ref('')

onMounted(() => {
  token.value = (route.query.token as string) ?? ''
  if (!token.value) {
    error.value = 'Недійсний або відсутній токен скидання.'
  }
})

async function handleSubmit() {
  error.value = ''
  if (newPassword.value !== confirmPassword.value) {
    error.value = 'Паролі не збігаються'
    return
  }
  if (newPassword.value.length < 8) {
    error.value = 'Пароль має містити мінімум 8 символів'
    return
  }
  loading.value = true
  try {
    await authApi.resetPassword(token.value, newPassword.value)
    done.value = true
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    if (typeof detail === 'string') {
      error.value = detail
    } else {
      error.value = e?.message || 'Щось пішло не так'
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-muted/30 relative overflow-hidden">
    <div class="absolute inset-0 overflow-hidden pointer-events-none">
      <div class="absolute -top-24 -right-24 w-96 h-96 bg-primary/5 rounded-full blur-3xl" />
      <div class="absolute -bottom-32 -left-32 w-[500px] h-[500px] bg-primary/10 rounded-full blur-3xl" />
    </div>

    <div class="relative w-full max-w-[420px] mx-4">
      <div class="text-center mb-8 flex flex-col items-center">
        <div class="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-primary text-primary-foreground mb-4 shadow-lg shadow-primary/20">
          <Sprout class="w-7 h-7" />
        </div>
        <h1 class="text-2xl font-bold text-foreground tracking-tight">Новий пароль</h1>
        <p class="text-sm text-muted-foreground mt-1">Оберіть надійний пароль</p>
      </div>

      <div class="bg-card rounded-xl shadow-xl border border-border p-8">
        <div v-if="done" class="text-center py-4 flex flex-col items-center gap-3">
          <p class="text-sm text-foreground font-medium">Пароль оновлено!</p>
          <p class="text-sm text-muted-foreground mb-2">Тепер ви можете увійти з новим паролем.</p>
          <Button class="w-full h-11" @click="router.push('/login')">Перейти до входу</Button>
        </div>

        <form v-else class="flex flex-col gap-5" @submit.prevent="handleSubmit">
          <div class="flex flex-col gap-1.5">
            <label class="text-sm font-medium">Новий пароль <span class="text-destructive">*</span></label>
            <Input v-model="newPassword" type="password" autocomplete="new-password"
              placeholder="••••••••" required class="h-11 w-full" />
          </div>

          <div class="flex flex-col gap-1.5">
            <label class="text-sm font-medium">Підтвердіть пароль <span class="text-destructive">*</span></label>
            <Input v-model="confirmPassword" type="password" autocomplete="new-password"
              placeholder="••••••••" required class="h-11 w-full" />
          </div>

          <p v-if="error" class="text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2 text-center border border-destructive/20">
            {{ error }}
          </p>

          <Button
            type="submit"
            :disabled="loading || !token"
            class="w-full h-11 mt-1 text-[15px] font-medium"
          >
            <Spinner v-if="loading" class="size-4 mr-2" />
            Встановити новий пароль
          </Button>
        </form>
      </div>
    </div>
  </div>
</template>
