<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useDocTypeStore } from '@/stores/doctype'
import client from '@/core/api/client'
import { FileText, Clock, TrendingUp } from 'lucide-vue-next'

interface ActivityEntry {
  id: string
  doctype: string
  doc_id: string
  action: string
  user: string
  created_at: string | null
}

const auth = useAuthStore()
const dtStore = useDocTypeStore()
const router = useRouter()

const docCounts = ref<Record<string, number>>({})
const recentActivity = ref<ActivityEntry[]>([])
const loadingActivity = ref(false)

async function loadCounts() {
  for (const dt of dtStore.doctypes) {
    try {
      const r = await client.get(`/api/v1/docs/${dt.name}`, { params: { per_page: 1 } })
      docCounts.value[dt.name] = r.data?.meta?.total ?? 0
    } catch {
      docCounts.value[dt.name] = 0
    }
  }
}

async function loadActivity() {
  loadingActivity.value = true
  try {
    const r = await client.get('/api/v1/docs/_activity/recent', { params: { limit: 10 } })
    recentActivity.value = (r.data?.data ?? []) as ActivityEntry[]
  } catch {
    // endpoint may not be implemented — ignore
  } finally {
    loadingActivity.value = false
  }
}

onMounted(async () => {
  await dtStore.loadAll()
  await loadCounts()
  await loadActivity()
})

function actionLabel(action: string): string {
  const map: Record<string, string> = { create: 'створив', update: 'оновив', delete: 'видалив' }
  return map[action] ?? action
}

function actionColor(action: string): string {
  const map: Record<string, string> = {
    create: 'text-emerald-600 bg-emerald-50',
    update: 'text-blue-600 bg-blue-50',
    delete: 'text-destructive bg-destructive/8'
  }
  return map[action] ?? 'text-muted-foreground bg-muted'
}
</script>

<template>
  <div class="p-8 max-w-5xl">
    <!-- Header -->
    <div class="mb-8">
      <h1 class="text-2xl font-semibold text-foreground mb-1">
        Вітаємо, {{ auth.user?.full_name ?? 'користувач' }}
      </h1>
      <p class="text-sm text-muted-foreground">Оберіть розділ нижче або у меню зліва</p>
    </div>

    <!-- DocType summary cards -->
    <div class="mb-10">
      <div class="flex items-center gap-2 mb-4">
        <TrendingUp class="w-4 h-4 text-muted-foreground" />
        <h2 class="text-sm font-semibold text-muted-foreground uppercase tracking-wider">Огляд</h2>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        <div
          v-for="dt in dtStore.doctypes"
          :key="dt.name"
          class="bg-card border border-border rounded-lg p-4 cursor-pointer hover:border-primary/40 hover:shadow-sm group transition-all duration-200"
          @click="router.push(`/${dt.name}`)"
        >
          <div class="flex items-start justify-between mb-3">
            <div class="w-8 h-8 rounded-md bg-primary/8 flex items-center justify-center">
              <FileText class="w-4 h-4 text-primary" />
            </div>
          </div>
          <p class="text-[13px] text-muted-foreground mb-0.5">{{ dt.module }}</p>
          <h3 class="text-sm font-semibold text-foreground mb-2 leading-tight">{{ dt.label }}</h3>
          <p class="text-2xl font-bold text-foreground tabular-nums">
            {{ docCounts[dt.name] ?? '—' }}
          </p>
          <p class="text-[11px] text-muted-foreground/70 mt-0.5">записів</p>
        </div>
      </div>
    </div>

    <!-- Recent activity feed -->
    <div v-if="recentActivity.length > 0">
      <div class="flex items-center gap-2 mb-4">
        <Clock class="w-4 h-4 text-muted-foreground" />
        <h2 class="text-sm font-semibold text-muted-foreground uppercase tracking-wider">Остання активність</h2>
      </div>
      <div class="bg-card border border-border rounded-lg overflow-hidden">
        <div
          v-for="entry in recentActivity"
          :key="entry.id"
          class="flex items-center gap-3 px-4 py-2.5 border-b border-border last:border-0 text-sm hover:bg-muted/40 transition-colors"
        >
          <span class="text-xs text-muted-foreground/60 whitespace-nowrap w-32 flex-shrink-0 tabular-nums">
            {{ entry.created_at ? new Date(entry.created_at).toLocaleString('uk-UA', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—' }}
          </span>
          <span class="font-medium text-foreground flex-shrink-0">{{ entry.user }}</span>
          <span
            class="text-[11px] px-1.5 py-0.5 rounded font-medium flex-shrink-0"
            :class="actionColor(entry.action)"
          >{{ actionLabel(entry.action) }}</span>
          <span class="text-muted-foreground truncate">{{ entry.doctype }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
