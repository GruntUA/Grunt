<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useWorkspaceStore } from '@/stores/workspace'
import client from '@/core/api/client'
import {
  Clock,
  TrendingUp,
  LayoutDashboard,
  ArrowRight,
  Sparkles,
  Command
} from 'lucide-vue-next'
import { Button } from '@/components/ui/button'

interface ActivityEntry {
  id: string
  doctype: string
  doc_id: string
  action: string
  user: string
  created_at: string | null
}

const auth = useAuthStore()
const wsStore = useWorkspaceStore()
const router = useRouter()

const recentActivity = ref<ActivityEntry[]>([])
const loadingActivity = ref(false)

async function loadActivity() {
  loadingActivity.value = true
  try {
    const r = await client.get('/api/v1/docs/_activity/recent', { params: { limit: 12 } })
    recentActivity.value = (r.data?.data ?? []) as ActivityEntry[]
  } catch {
    // endpoint may not be implemented
  } finally {
    loadingActivity.value = false
  }
}

onMounted(async () => {
  await wsStore.loadAll()
  await loadActivity()
})

const timeGreeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 12) return 'Доброго ранку'
  if (hour < 18) return 'Доброго дня'
  return 'Доброго вечора'
})

function actionConfig(action: string) {
  const map: Record<string, { label: string; color: string }> = {
    create: { label: 'створив', color: 'bg-emerald-500/10 text-emerald-600' },
    update: { label: 'оновив', color: 'bg-blue-500/10 text-indigo-600' },
    delete: { label: 'видалив', color: 'bg-red-500/10 text-destructive' }
  }
  return map[action] ?? { label: action, color: 'bg-muted text-muted-foreground' }
}
</script>

<template>
  <div class="p-8 max-w-7xl mx-auto">
    <!-- Header -->
    <header class="mb-12 flex flex-col md:flex-row md:items-end justify-between gap-6">
      <div class="space-y-1">
        <div class="flex items-center gap-2 text-primary font-bold text-xs uppercase tracking-[0.2em] mb-2">
          <Sparkles class="size-3.5" />
          <span>Система активована</span>
        </div>
        <h1 class="text-4xl font-extrabold tracking-tight text-foreground lg:text-5xl">
          {{ timeGreeting }}, {{ auth.user?.full_name?.split(' ')[0] ?? 'користувач' }}
        </h1>
        <p class="text-muted-foreground text-lg font-medium">
          Ваш персональний центр управління Grunt. Оберіть робочий простір для початку.
        </p>
      </div>

      <div class="flex items-center gap-3">
        <Button variant="outline" class="rounded-xl shadow-sm border-sidebar-border h-11 px-5"
          @click="router.push('/settings')">
          <Command class="size-4 mr-2 opacity-50" />
          ПанельStudio
        </Button>
      </div>
    </header>

    <div class="grid grid-cols-1 lg:grid-cols-12 gap-10">
      <!-- Left Column: Workspaces -->
      <div class="lg:col-span-8 space-y-10">
        <section>
          <div class="flex items-center justify-between mb-6">
            <div class="flex items-center gap-3">
              <div class="p-2 rounded-xl bg-primary/10">
                <LayoutDashboard class="size-5 text-primary" />
              </div>
              <h2 class="text-xl font-bold tracking-tight">Робочі простори</h2>
            </div>
            <Button variant="ghost" size="sm"
              class="text-xs font-semibold text-primary/70 hover:text-primary transition-colors">
              Всі простори
              <ArrowRight class="size-3 ml-1.5" />
            </Button>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div v-for="ws in wsStore.workspaces" :key="ws.name"
              class="group relative bg-card border border-sidebar-border rounded-2xl p-6 cursor-pointer hover:border-primary/30 transition-all duration-300 shadow-sm hover:shadow-xl hover:-translate-y-1"
              @click="router.push(`/${ws.name}/desk`)">
              <div class="flex items-start justify-between mb-6">
                <div
                  class="size-14 rounded-2xl flex items-center justify-center text-3xl shadow-inner transition-transform group-hover:scale-110 duration-300"
                  :style="{ backgroundColor: ws.color + '15', color: ws.color }">
                  {{ ws.icon || '📁' }}
                </div>
                <div class="opacity-0 group-hover:opacity-100 transition-opacity bg-primary/5 p-2 rounded-full">
                  <ArrowRight class="size-4 text-primary" />
                </div>
              </div>

              <div class="space-y-1.5">
                <h3 class="text-lg font-bold text-foreground group-hover:text-primary transition-colors line-clamp-1">
                  {{ ws.label }}
                </h3>
                <p class="text-sm text-muted-foreground line-clamp-2 leading-relaxed min-h-[40px]">
                  {{ ws.description || `Управління даними в розділі ${ws.label}.` }}
                </p>
              </div>

              <!-- Visual Accent -->
              <div
                class="absolute bottom-0 left-6 right-6 h-1 rounded-t-full transition-transform scale-x-0 group-hover:scale-x-100 duration-500"
                :style="{ backgroundColor: ws.color }"></div>
            </div>
          </div>
        </section>
      </div>

      <!-- Right Column: Stats & Activity -->
      <div class="lg:col-span-4 space-y-10">
        <!-- Recent Activity Feed -->
        <section class="bg-card border border-sidebar-border rounded-3xl overflow-hidden shadow-sm">
          <div class="p-6 border-b border-sidebar-border flex items-center gap-3">
            <div class="p-2 rounded-xl bg-orange-500/10">
              <Clock class="size-5 text-orange-600" />
            </div>
            <h2 class="text-lg font-bold tracking-tight">Активність</h2>
          </div>

          <div class="divide-y divide-sidebar-border">
            <div v-for="entry in recentActivity" :key="entry.id"
              class="p-4 hover:bg-muted/40 transition-colors flex flex-col gap-2">
              <div class="flex items-center justify-between">
                <span class="text-xs font-bold text-foreground">{{ entry.user }}</span>
                <span class="text-[10px] text-muted-foreground/60 tabular-nums">
                  {{ entry.created_at ? new Date(entry.created_at).toLocaleTimeString('uk-UA', {
                    hour: '2-digit',
                    minute: '2-digit' }) : '' }}
                </span>
              </div>
              <div class="flex items-center gap-2">
                <span class="text-[9px] px-1.5 py-0.5 rounded-full font-bold uppercase tracking-wider shrink-0"
                  :class="actionConfig(entry.action).color">
                  {{ actionConfig(entry.action).label }}
                </span>
                <span class="text-xs text-muted-foreground truncate">{{ entry.doctype }}</span>
              </div>
            </div>

            <div v-if="recentActivity.length === 0" class="p-12 text-center text-muted-foreground italic text-sm">
              Немає недавньої активності
            </div>
          </div>

          <div class="p-4 bg-muted/20 border-t border-sidebar-border">
            <Button variant="ghost" size="xs" class="w-full text-xs font-bold text-muted-foreground hover:text-primary">
              Переглянути весь лог
            </Button>
          </div>
        </section>

        <!-- Stats Card -->
        <div class="bg-primary/5 border border-primary/10 rounded-3xl p-6 relative overflow-hidden group">
          <div class="relative z-10">
            <TrendingUp class="size-6 text-primary mb-4" />
            <h3 class="text-lg font-bold text-primary mb-1">Статус сервера</h3>
            <p class="text-sm text-primary/70 mb-4">Всі системи працюють стабільно. Оновлень бази даних не потрібно.</p>
            <div class="h-1.5 w-full bg-primary/10 rounded-full overflow-hidden">
              <div class="h-full bg-primary w-full animate-pulse"></div>
            </div>
          </div>
          <div
            class="absolute -right-6 -bottom-6 size-24 bg-primary/10 rounded-full blur-2xl group-hover:bg-primary/20 transition-all duration-500">
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
