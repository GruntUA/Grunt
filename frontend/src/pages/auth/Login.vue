<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { FormField } from '@/components/ui/form-field'
import { Loader2 } from 'lucide-vue-next'

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
  <div class="min-h-screen flex items-center justify-center bg-muted">
    <div class="w-[400px] bg-card rounded-lg shadow-md p-8">
      <div class="text-center mb-8">
        <h1 class="text-2xl font-bold text-primary">Ґрунт</h1>
        <p class="text-sm text-muted-foreground mt-1">Увійдіть у систему</p>
      </div>

      <form class="flex flex-col gap-4" @submit.prevent="handleLogin">
        <FormField label="Email" required>
          <template #default="{ id }">
            <Input :id="id" v-model="email" type="email" placeholder="admin@grunt.local" required />
          </template>
        </FormField>

        <FormField label="Пароль" required>
          <template #default="{ id }">
            <Input :id="id" v-model="password" type="password" placeholder="••••••••" required />
          </template>
        </FormField>

        <p v-if="error" class="text-sm text-destructive text-center">{{ error }}</p>

        <Button type="submit" :disabled="loading" class="w-full mt-2">
          <Loader2 v-if="loading" class="mr-2 h-4 w-4 animate-spin" />
          Увійти
        </Button>
      </form>
    </div>
  </div>
</template>
