<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { FormField } from '@/components/ui/form-field'
import { Loader2 } from 'lucide-vue-next'
import client from '@/core/api/client'

const router = useRouter()

// ── State ─────────────────────────────────────────────────────────────────

const step = ref<'qr' | 'confirm' | 'backup'>('qr')
const qrSvg = ref('')
const secret = ref('')
const code = ref('')
const backupCodes = ref<string[]>([])
const loading = ref(false)
const error = ref('')

// ── Init ──────────────────────────────────────────────────────────────────

onMounted(async () => {
  loading.value = true
  try {
    const { data } = await client.post('/api/v1/auth/mfa/setup')
    secret.value = data.data.secret
    qrSvg.value = data.data.qr_svg
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Failed to start MFA setup.'
  } finally {
    loading.value = false
  }
})

// ── Confirm ───────────────────────────────────────────────────────────────

async function handleConfirm() {
  error.value = ''
  loading.value = true
  try {
    const { data } = await client.post('/api/v1/auth/mfa/confirm', { code: code.value })
    backupCodes.value = data.data.backup_codes
    step.value = 'backup'
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Invalid code. Try again.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-background p-6">
    <div class="w-full max-w-md space-y-6">

      <!-- Step 1: Scan QR -->
      <template v-if="step === 'qr'">
        <div class="text-center">
          <h1 class="text-2xl font-semibold tracking-tight">Set up two-factor authentication</h1>
          <p class="text-sm text-muted-foreground mt-1">
            Scan this QR code with your authenticator app (Google Authenticator, Authy, etc.)
          </p>
        </div>

        <div v-if="loading" class="flex justify-center py-8">
          <Loader2 class="size-8 animate-spin text-muted-foreground" />
        </div>

        <!-- QR SVG or URI fallback -->
        <div v-else class="flex flex-col items-center gap-4">
          <!-- SVG QR code -->
          <div
            v-if="qrSvg.startsWith('<svg')"
            class="rounded-lg border p-4 bg-white"
            v-html="qrSvg"
          />
          <!-- URI fallback -->
          <div v-else class="rounded-lg border p-4 text-xs break-all text-muted-foreground max-w-xs">
            {{ qrSvg }}
          </div>

          <div class="text-center">
            <p class="text-xs text-muted-foreground mb-1">Or enter the key manually:</p>
            <code class="text-sm font-mono bg-muted px-2 py-1 rounded select-all">{{ secret }}</code>
          </div>
        </div>

        <p v-if="error" class="text-sm text-destructive text-center">{{ error }}</p>

        <Button class="w-full" :disabled="loading || !secret" @click="step = 'confirm'">
          Next — enter verification code
        </Button>
      </template>

      <!-- Step 2: Verify first code -->
      <template v-else-if="step === 'confirm'">
        <div class="text-center">
          <h1 class="text-2xl font-semibold tracking-tight">Verify setup</h1>
          <p class="text-sm text-muted-foreground mt-1">
            Enter the 6-digit code shown in your authenticator app to confirm.
          </p>
        </div>

        <form class="space-y-4" @submit.prevent="handleConfirm">
          <FormField label="Verification code">
            <Input
              v-model="code"
              placeholder="000000"
              maxlength="6"
              autocomplete="one-time-code"
              inputmode="numeric"
              class="text-center tracking-widest text-lg"
              autofocus
            />
          </FormField>

          <p v-if="error" class="text-sm text-destructive text-center">{{ error }}</p>

          <div class="flex gap-2">
            <Button type="button" variant="outline" class="flex-1" @click="step = 'qr'">Back</Button>
            <Button type="submit" class="flex-1" :disabled="loading || !code">
              <Loader2 v-if="loading" class="mr-2 size-4 animate-spin" />
              Confirm
            </Button>
          </div>
        </form>
      </template>

      <!-- Step 3: Backup codes -->
      <template v-else-if="step === 'backup'">
        <div class="text-center">
          <h1 class="text-2xl font-semibold tracking-tight">Save your backup codes</h1>
          <p class="text-sm text-muted-foreground mt-1">
            Store these codes in a safe place. Each can only be used once if you lose access to your
            authenticator app.
          </p>
        </div>

        <div class="rounded-lg border bg-muted/40 p-4 grid grid-cols-2 gap-2">
          <code
            v-for="c in backupCodes"
            :key="c"
            class="font-mono text-sm text-center py-1 px-2 bg-background rounded border select-all"
          >{{ c }}</code>
        </div>

        <Button class="w-full" @click="router.push('/')">
          Done — go to home
        </Button>
      </template>

    </div>
  </div>
</template>
