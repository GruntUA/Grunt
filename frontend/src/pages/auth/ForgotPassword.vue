<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { authApi } from '@/core/api/auth-admin'
import { Sprout, ArrowLeft } from '@lucide/vue'

const router = useRouter()

const email = ref('')
const loading = ref(false)
const sent = ref(false)
const error = ref('')

async function handleSubmit() {
  error.value = ''
  loading.value = true
  try {
    await authApi.forgotPassword(email.value)
    sent.value = true
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || 'Something went wrong'
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
        <h1 class="text-2xl font-bold text-foreground tracking-tight">Скинути пароль</h1>
        <p class="text-sm text-muted-foreground mt-1">Ми надішлемо вам посилання для відновлення</p>
      </div>

      <div class="bg-card rounded-xl shadow-xl border border-border p-8">
        <div v-if="sent" class="text-center py-4 flex flex-col items-center gap-3">
          <p class="text-sm text-foreground font-medium">Перевірте пошту</p>
          <p class="text-sm text-muted-foreground">
            Якщо акаунт з <strong>{{ email }}</strong> існує, ми надіслали посилання для зміни пароля.
          </p>
          <Button variant="text" class="mt-2" label="Повернутись до входу" @click="router.push('/login')" />
        </div>

        <form v-else class="flex flex-col gap-5" @submit.prevent="handleSubmit">
          <div class="flex flex-col gap-1.5">
            <label class="text-sm font-medium">Email <span class="text-destructive">*</span></label>
            <InputText v-model="email" type="email" placeholder="you@example.com" required class="h-11 w-full" />
          </div>

          <p v-if="error" class="text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2 text-center border border-destructive/20">
            {{ error }}
          </p>

          <Button type="submit" :loading="loading" class="w-full h-11 mt-1 text-[15px] font-medium" label="Надіслати посилання" />

          <button
            type="button"
            class="flex items-center justify-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors mt-2"
            @click="router.push('/login')"
          >
            <ArrowLeft class="size-3.5" />
            Повернутись до входу
          </button>
        </form>
      </div>
    </div>
  </div>
</template>
