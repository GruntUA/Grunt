<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { authApi } from '@/core/api/auth-admin'
import { ArrowLeft } from '@lucide/vue'
import AppBrand from '@/components/app/AppBrand.vue'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'

const { t } = useI18n()

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
    error.value = e?.response?.data?.error?.message || e?.response?.data?.detail || e?.message || 'Something went wrong'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="bg-muted flex min-h-svh flex-col items-center justify-center gap-6 p-6 md:p-10">
    <div class="flex w-full max-w-sm flex-col gap-6">
      <AppBrand class="self-center" />

      <Card>
        <CardHeader class="text-center">
          <CardTitle class="text-xl">{{ sent ? t('Check your email') : t('Reset password') }}</CardTitle>
          <CardDescription>
            {{ sent ? t('If an account with {email} exists, we have sent a password reset link.', { email }) : t('We will send you a recovery link') }}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button v-if="sent" variant="outline" class="w-full" @click="router.push('/login')">{{ t('Back to sign in') }}</Button>

          <form v-else @submit.prevent="handleSubmit">
            <FieldGroup>
              <Field>
                <FieldLabel for="forgot-email">Email</FieldLabel>
                <Input id="forgot-email" v-model="email" type="email" autocomplete="username" placeholder="you@example.com" required />
              </Field>

              <Alert v-if="error" variant="destructive">
                <AlertDescription>{{ error }}</AlertDescription>
              </Alert>

              <Field>
                <Button type="submit" :disabled="loading">
                  <Spinner v-if="loading" />
                  {{ t('Send link') }}
                </Button>
                <Button type="button" variant="ghost" @click="router.push('/login')">
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
