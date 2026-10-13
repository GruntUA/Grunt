<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { authApi } from '@/core/api/auth-admin'
import AppBrand from '@/components/app/AppBrand.vue'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'

const { t } = useI18n()

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
    error.value = t('Invalid or missing reset token.')
  }
})

async function handleSubmit() {
  error.value = ''
  if (newPassword.value !== confirmPassword.value) {
    error.value = t('Passwords do not match')
    return
  }
  if (newPassword.value.length < 8) {
    error.value = t('Password must be at least 8 characters')
    return
  }
  loading.value = true
  try {
    await authApi.resetPassword(token.value, newPassword.value)
    done.value = true
  } catch (e: any) {
    const body = e?.response?.data
    const detail = body?.error?.message ?? body?.detail
    if (typeof detail === 'string') {
      error.value = detail
    } else {
      error.value = e?.message || t('Something went wrong')
    }
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
          <CardTitle class="text-xl">{{ done ? t('Password updated!') : t('New password') }}</CardTitle>
          <CardDescription>
            {{ done ? t('You can now sign in with your new password.') : t('Choose a strong password') }}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button v-if="done" class="w-full" @click="router.push('/login')">{{ t('Go to sign in') }}</Button>

          <form v-else @submit.prevent="handleSubmit">
            <FieldGroup>
              <Field>
                <FieldLabel for="reset-password">{{ t('New password') }}</FieldLabel>
                <Input id="reset-password" v-model="newPassword" type="password" autocomplete="new-password"
                  placeholder="••••••••" required />
              </Field>
              <Field>
                <FieldLabel for="reset-password-confirm">{{ t('Confirm password') }}</FieldLabel>
                <Input id="reset-password-confirm" v-model="confirmPassword" type="password" autocomplete="new-password"
                  placeholder="••••••••" required />
              </Field>

              <Alert v-if="error" variant="destructive">
                <AlertDescription>{{ error }}</AlertDescription>
              </Alert>

              <Button type="submit" :disabled="loading || !token">
                <Spinner v-if="loading" />
                {{ t('Set new password') }}
              </Button>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
