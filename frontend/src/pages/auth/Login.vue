<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import GInput from '@/components/ui/GInput.vue'
import GButton from '@/components/ui/GButton.vue'

const router = useRouter()
const auth = useAuthStore()

const email = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(email.value, password.value)
    router.push('/')
  } catch {
    error.value = 'Невірний email або пароль'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-[--grunt-surface-secondary]">
    <div class="w-[400px] bg-[--grunt-surface] rounded-[--grunt-radius-lg] shadow-[--grunt-shadow-md] p-8">
      <div class="text-center mb-8">
        <h1 class="text-2xl font-bold text-[--grunt-primary]">Ґрунт</h1>
        <p class="text-sm text-[--grunt-text-secondary] mt-1">Увійдіть у систему</p>
      </div>

      <form class="flex flex-col gap-4" @submit.prevent="handleLogin">
        <GInput v-model="email" label="Email" type="email" placeholder="admin@grunt.local" required />
        <GInput v-model="password" label="Пароль" type="password" placeholder="••••••••" required />

        <p v-if="error" class="text-sm text-[--grunt-danger] text-center">{{ error }}</p>

        <GButton type="submit" :loading="loading" class="w-full mt-2">Увійти</GButton>
      </form>
    </div>
  </div>
</template>
