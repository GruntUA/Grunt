<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import api from '@/core/api/client'
import { useToast } from '@/core/composables/useToast'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import {
  Monitor,
  Smartphone,
  Globe,
  LogOut,
  Shield,
  Loader2,
  Trash2,
} from '@lucide/vue'

const { t } = useI18n()
const auth = useAuthStore()
const toast = useToast()

interface UserSession {
  id: string
  ip_address: string
  user_agent: string
  last_active_at: string | null
  creation: string
}

const sessions = ref<UserSession[]>([])
const loadingSessions = ref(false)
const revokingId = ref<string | null>(null)

async function loadSessions() {
  loadingSessions.value = true
  try {
    const res = await api.get('/api/v1/auth/sessions')
    sessions.value = res.data?.data ?? []
  } catch {
    toast.error(t('Failed to load sessions'))
  } finally {
    loadingSessions.value = false
  }
}

async function revokeSession(id: string) {
  revokingId.value = id
  try {
    await api.delete(`/api/v1/auth/sessions/${id}`)
    sessions.value = sessions.value.filter(s => s.id !== id)
    toast.success(t('Session terminated'))
  } catch {
    toast.error(t('Failed to terminate session'))
  } finally {
    revokingId.value = null
  }
}

async function revokeAll() {
  if (!confirm(t('Terminate all other sessions?'))) return
  loadingSessions.value = true
  try {
    // Revoke each session except (we keep current — server handles this by checking session_key)
    const toRevoke = sessions.value.slice()
    for (const s of toRevoke) {
      await api.delete(`/api/v1/auth/sessions/${s.id}`)
    }
    sessions.value = []
    toast.success(t('All sessions terminated'))
  } catch {
    toast.error(t('Operation failed'))
  } finally {
    loadingSessions.value = false
  }
}

function formatDate(dt: string | null): string {
  if (!dt) return '—'
  return new Date(dt).toLocaleString('uk-UA', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function parseUserAgent(ua: string): { browser: string; os: string; isMobile: boolean } {
  const mobile = /mobile|android|iphone|ipad/i.test(ua)
  const browser = ua.includes('Chrome')
    ? 'Chrome'
    : ua.includes('Firefox')
      ? 'Firefox'
      : ua.includes('Safari')
        ? 'Safari'
        : ua.includes('Edge')
          ? 'Edge'
          : 'Browser'
  const os = ua.includes('Windows')
    ? 'Windows'
    : ua.includes('Mac')
      ? 'macOS'
      : ua.includes('Linux')
        ? 'Linux'
        : ua.includes('Android')
          ? 'Android'
          : ua.includes('iOS') || ua.includes('iPhone')
            ? 'iOS'
            : 'Unknown OS'
  return { browser, os, isMobile: mobile }
}

onMounted(loadSessions)
</script>

<template>
  <div class="max-w-2xl mx-auto py-10 px-6">
    <!-- Header -->
    <div class="mb-8">
      <div class="flex items-center gap-3 mb-1">
        <div
          class="w-14 h-14 rounded-full bg-gradient-to-br from-primary to-emerald-700 text-primary-foreground text-xl font-bold flex items-center justify-center shadow"
        >
          {{ auth.user?.full_name?.charAt(0).toUpperCase() ?? '?' }}
        </div>
        <div>
          <h1 class="text-xl font-bold text-foreground">{{ auth.user?.full_name }}</h1>
          <p class="text-sm text-muted-foreground">{{ auth.user?.email }}</p>
        </div>
      </div>
    </div>

    <Separator class="mb-8" />

    <!-- Sessions -->
    <section>
      <div class="flex items-center justify-between mb-4">
        <div class="flex items-center gap-2">
          <Shield class="size-5 text-primary" />
          <h2 class="text-base font-semibold text-foreground">{{ t('Active sessions') }}</h2>
          <Badge v-if="sessions.length" variant="secondary">{{ sessions.length }}</Badge>
        </div>
        <div class="flex items-center gap-2">
          <Button
            v-if="sessions.length > 1"
            variant="outline"
            size="sm"
            class="text-xs text-destructive hover:bg-destructive/5 hover:text-destructive border-destructive/30"
            @click="revokeAll"
          >
            <LogOut class="size-3.5 mr-1.5" />
            {{ t('Terminate all') }}
          </Button>
          <Button variant="ghost" size="sm" class="text-xs" :disabled="loadingSessions" @click="loadSessions">
            <Loader2 v-if="loadingSessions" class="size-3.5 mr-1.5 animate-spin" />
            {{ t('Refresh') }}
          </Button>
        </div>
      </div>

      <!-- Loading skeleton -->
      <div v-if="loadingSessions && sessions.length === 0" class="space-y-3">
        <div v-for="i in 3" :key="i" class="h-20 rounded-xl bg-muted/50 animate-pulse" />
      </div>

      <!-- Empty -->
      <div
        v-else-if="!loadingSessions && sessions.length === 0"
        class="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground"
      >
        {{ t('No active sessions') }}
      </div>

      <!-- Session cards -->
      <div v-else class="space-y-2">
        <div
          v-for="session in sessions"
          :key="session.id"
          class="group flex items-start justify-between gap-4 rounded-xl border border-border/60 bg-card px-4 py-3.5 hover:border-border transition-colors"
        >
          <div class="flex items-start gap-3 min-w-0">
            <!-- Device icon -->
            <div class="mt-0.5 size-9 rounded-lg bg-muted flex items-center justify-center shrink-0">
              <component
                :is="parseUserAgent(session.user_agent ?? '').isMobile ? Smartphone : Monitor"
                class="size-4 text-muted-foreground"
              />
            </div>

            <div class="min-w-0">
              <p class="text-sm font-medium text-foreground leading-tight">
                {{ parseUserAgent(session.user_agent ?? '').browser }}
                <span class="text-muted-foreground font-normal">·</span>
                {{ parseUserAgent(session.user_agent ?? '').os }}
              </p>
              <div class="flex items-center gap-1.5 mt-1 text-xs text-muted-foreground">
                <Globe class="size-3 shrink-0" />
                <span>{{ session.ip_address || '—' }}</span>
              </div>
              <p class="text-xs text-muted-foreground mt-0.5">
                {{ t('Last active') }}: {{ formatDate(session.last_active_at) }}
              </p>
            </div>
          </div>

          <!-- Revoke button -->
          <Button
            variant="ghost"
            size="sm"
            class="opacity-0 group-hover:opacity-100 text-xs text-muted-foreground hover:text-destructive hover:bg-destructive/5 transition-all shrink-0"
            :disabled="revokingId === session.id"
            @click="revokeSession(session.id)"
          >
            <Loader2 v-if="revokingId === session.id" class="size-3.5 animate-spin" />
            <Trash2 v-else class="size-3.5" />
          </Button>
        </div>
      </div>
    </section>
  </div>
</template>
