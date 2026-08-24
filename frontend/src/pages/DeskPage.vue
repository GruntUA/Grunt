<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import { useUIStore } from '@/stores/ui'
import { workspaceApi } from '@/core/api/workspace'
import AppCard from '@/components/desk/AppCard.vue'
import ActivityStream from '@/components/dashboard/ActivityStream.vue'
import MyWorkPanel from '@/components/dashboard/MyWorkPanel.vue'
import { readRecent, looksLikeId, type RecentDoc } from '@/core/recentDocs'
import { Clock, Search, Zap, LayoutGrid, ArrowRight } from '@lucide/vue'

const auth = useAuthStore()
const appStore = useAppStore()
const uiStore = useUIStore()
const router = useRouter()

const allCounts = ref<Record<string, Record<string, number>>>({})

const recentDocs = ref<RecentDoc[]>([])

const greeting = computed(() => {
  const hour = new Date().getHours()
  const name = auth.user?.full_name?.split(' ')[0] ?? 'користувач'
  if (hour < 5) return { text: `Добраніч, ${name}`, emoji: '🌙' }
  if (hour < 12) return { text: `Доброго ранку, ${name}`, emoji: '☀️' }
  if (hour < 18) return { text: `Доброго дня, ${name}`, emoji: '🌤️' }
  return { text: `Доброго вечора, ${name}`, emoji: '🌆' }
})

// Honest, deduplicated business-document total (excludes logs/sessions/config).
// Falls back to summing per-workspace counts if the stats call fails.
const businessDocsTotal = ref<number | null>(null)
const totalDocsCount = computed(() => {
  if (businessDocsTotal.value !== null) return businessDocsTotal.value
  let total = 0
  for (const ws of Object.values(allCounts.value)) {
    total += Object.values(ws).reduce((s, v) => s + v, 0)
  }
  return total
})

const quickStats = computed(() => [
  { label: 'Додатків', value: appStore.workspaces.length, color: '#6366f1' },
  { label: 'Документів', value: totalDocsCount.value, color: '#10b981' },
  { label: 'Нещодавніх', value: recentDocs.value.length, color: '#f59e0b' },
])

onMounted(async () => {
  document.title = 'Головна — Grunt'

  await appStore.loadAll()

  // Read history, dropping entries whose workspace is no longer installed.
  recentDocs.value = readRecent(appStore.workspaces.map(w => w.name))

  // Fire all count requests at once instead of walking workspaces serially —
  // they are independent, so serial awaits only added round-trips.
  const [counts] = await Promise.all([
    Promise.all(
      appStore.workspaces.map(async ws =>
        [ws.name, await workspaceApi.getCounts(ws.name).catch(() => ({}))] as const
      )
    ),
    workspaceApi.getDocumentStats()
      .then(s => { businessDocsTotal.value = s.total })
      .catch(() => { /* keep the per-workspace fallback in totalDocsCount */ }),
  ])
  allCounts.value = Object.fromEntries(counts)
})

function timeAgo(ts: number): string {
  const diff = Date.now() - ts
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return 'щойно'
  if (minutes < 60) return `${minutes} хв`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} год`
  const days = Math.floor(hours / 24)
  return `${days} дн`
}

function findWorkspaceForDoc(doc: RecentDoc) {
  return appStore.workspaces.find(w => w.name === doc.workspace)
}

// Returns a human-readable display title for a document.
// Falls back to "DocType · short-id" when the title is blank or looks like an
// opaque id (UUID or hash name).
function hasRealTitle(doc: RecentDoc): boolean {
  return !!doc.title && !looksLikeId(doc.title)
}

function docDisplayTitle(doc: RecentDoc): string {
  if (hasRealTitle(doc)) return doc.title
  return `${doc.doctype} · ${doc.id.slice(0, 8)}`
}

function docInitials(doc: RecentDoc): string {
  if (hasRealTitle(doc)) return doc.title.slice(0, 2).toUpperCase()
  return doc.doctype.slice(0, 2).toUpperCase()
}
</script>

<template>
  <div class="overflow-y-auto bg-background h-screen">

    <!-- Ambient background blobs -->
    <div class="fixed inset-0 pointer-events-none overflow-hidden -z-10">
      <div class="absolute -top-40 -right-40 w-96 h-96 bg-primary/5 rounded-full blur-[120px]" />
      <div class="absolute top-1/2 -left-40 w-80 h-80 bg-violet-500/5 rounded-full blur-[100px]" />
      <div class="absolute bottom-0 right-1/3 w-72 h-72 bg-emerald-500/5 rounded-full blur-[80px]" />
    </div>

      <main class="max-w-6xl mx-auto px-6 py-8 md:py-12 space-y-10">

        <!-- ── HERO SECTION ─────────────────────────────────────────── -->
        <section>
          <div class="flex items-start gap-4 mb-8">

            <div class="flex-1">
              <!-- Greeting -->
              <div class="flex items-center gap-3 mb-1">
                <span class="text-4xl">{{ greeting.emoji }}</span>
                <h1 class="text-3xl md:text-4xl font-semibold text-foreground tracking-tight leading-none">
                  {{ greeting.text }}
                </h1>
              </div>
              <p class="text-sm text-muted-foreground/70 ml-[3.5rem] font-medium">
                Що плануєте зробити сьогодні?
              </p>
            </div>
          </div>

          <!-- Search bar -->
          <div class="relative group cursor-pointer" @click="uiStore.openCommandPalette">
            <div
              class="relative flex items-center gap-4 px-5 py-4 bg-card/80 border border-border/50 rounded-lg shadow-sm transition-colors duration-300 group-hover:border-primary/40 group-hover:shadow-md">
              <div
                class="size-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0 transition-colors group-hover:bg-primary/20">
                <Search class="size-4 text-primary/70 group-hover:text-primary transition-colors" />
              </div>
              <span class="text-sm text-muted-foreground/50 flex-1 font-medium">
                Шукайте документи, додатки або дії...
              </span>
              <div class="hidden sm:flex items-center gap-1 shrink-0">
                <kbd
                  class="px-2 py-1 rounded-lg bg-muted/60 text-xs font-semibold text-muted-foreground border border-border/40 shadow-sm">⌘</kbd>
                <kbd
                  class="px-2 py-1 rounded-lg bg-muted/60 text-xs font-semibold text-muted-foreground border border-border/40 shadow-sm">K</kbd>
              </div>
            </div>
          </div>

          <!-- Quick stats -->
          <div class="mt-5 flex items-center gap-3 flex-wrap">
            <div v-for="stat in quickStats" :key="stat.label"
              class="flex items-center gap-2 px-4 py-2 rounded-lg bg-card/50 border border-border/30">
              <div class="size-2 rounded-full" :style="{ backgroundColor: stat.color }" />
              <span class="text-xs text-muted-foreground/60 font-medium">{{ stat.label }}:</span>
              <span class="text-xs font-semibold text-foreground tabular-nums">{{ stat.value }}</span>
            </div>
            <div class="flex items-center gap-1.5 text-xs text-muted-foreground/40">
              <Zap class="size-3" />
              <span>Grunt</span>
            </div>
          </div>
        </section>

        <!-- ── MY WORK (personal) ───────────────────────────────────── -->
        <MyWorkPanel />

        <!-- ── WORKSPACE CARDS ──────────────────────────────────────── -->
        <section>
          <div class="flex items-center justify-between mb-5">
            <div class="flex items-center gap-2">
              <div class="size-7 rounded-lg bg-primary/10 flex items-center justify-center">
                <LayoutGrid class="size-3.5 text-primary/70" />
              </div>
              <h2 class="text-sm font-semibold text-foreground/70 uppercase tracking-widest">Ваші додатки</h2>
            </div>
            <span class="text-xs text-muted-foreground/40 font-medium">{{ appStore.workspaces.length }}
              встановлено</span>
          </div>

          <!-- Loading skeleton -->
          <div v-if="appStore.loading" class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            <div v-for="i in 4" :key="i" class="h-16 rounded-lg bg-card/50 border border-border/30 animate-pulse" />
          </div>

          <!-- Empty state -->
          <div v-else-if="appStore.workspaces.length === 0 && !auth.user?.is_superadmin"
            class="flex flex-col items-center justify-center py-20 rounded-lg border border-dashed border-border/40 text-center space-y-3">
            <div class="size-16 rounded-lg bg-muted/20 flex items-center justify-center text-3xl">📦</div>
            <p class="text-sm text-muted-foreground">Немає встановлених додатків</p>
          </div>

          <!-- Cards grid -->
          <div v-else class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            <AppCard v-for="ws in appStore.workspaces" :key="ws.name" :workspace="ws" :counts="allCounts[ws.name]" />
          </div>
        </section>

        <!-- ── BOTTOM GRID: Recent + Activity ──────────────────────── -->
        <div class="grid grid-cols-1 lg:grid-cols-5 gap-6 items-start pb-12">

          <!-- Recent documents -->
          <section class="lg:col-span-3">
            <div class="flex items-center justify-between mb-4">
              <div class="flex items-center gap-2">
                <div class="size-7 rounded-lg bg-amber-500/10 flex items-center justify-center">
                  <Clock class="size-3.5 text-amber-500/70" />
                </div>
                <h2 class="text-sm font-semibold text-foreground/70 uppercase tracking-widest">Нещодавні</h2>
              </div>
            </div>

            <!-- Empty state -->
            <div v-if="recentDocs.length === 0"
              class="flex flex-col items-center justify-center py-14 rounded-lg border border-dashed border-border/40 text-center space-y-2">
              <div class="size-12 rounded-lg bg-muted/20 flex items-center justify-center text-2xl">🕐</div>
              <p class="text-sm text-muted-foreground">Відкритих документів ще немає</p>
              <p class="text-xs text-muted-foreground/50">Перейдіть до будь-якого запису, і він з'явиться тут</p>
            </div>

            <div v-else class="rounded-lg border border-border/40 bg-card/60 overflow-hidden shadow-sm">
              <div v-for="doc in recentDocs.slice(0, 8)" :key="doc.id"
                class="group flex items-center gap-3 px-4 py-3 border-b border-border/20 last:border-0 hover:bg-primary/[0.03] cursor-pointer transition-all duration-200"
                @click="router.push(`/${doc.workspace}/${doc.doctype}/${doc.id}`)">
                <!-- Avatar -->
                <div
                  class="size-8 rounded-lg flex items-center justify-center text-xs font-semibold shrink-0"
                  :style="{
                    backgroundColor: `color-mix(in srgb, ${findWorkspaceForDoc(doc)?.color ?? '#6366f1'} 20%, transparent)`,
                    color: findWorkspaceForDoc(doc)?.color ?? '#6366f1'
                  }">
                  {{ docInitials(doc) }}
                </div>

                <!-- Info -->
                <div class="flex-1 min-w-0">
                  <p
                    class="text-sm font-semibold text-foreground truncate group-hover:text-primary transition-colors duration-200">
                    {{ docDisplayTitle(doc) }}
                  </p>
                  <div class="flex items-center gap-1.5 mt-0.5">
                    <span v-if="findWorkspaceForDoc(doc)"
                      class="text-xs font-semibold uppercase tracking-widest px-1.5 py-0.5 rounded-md" :style="{
                        backgroundColor: `color-mix(in srgb, ${findWorkspaceForDoc(doc)?.color ?? '#666'} 15%, transparent)`,
                        color: findWorkspaceForDoc(doc)?.color ?? '#666'
                      }">{{ findWorkspaceForDoc(doc)?.label }}</span>
                    <span class="text-xs text-muted-foreground/40 font-mono">{{ doc.doctype }}</span>
                  </div>
                </div>

                <!-- Time + arrow -->
                <div class="flex items-center gap-2 shrink-0">
                  <span class="text-xs text-muted-foreground/40 font-mono tabular-nums">{{ timeAgo(doc.ts) }}</span>
                  <ArrowRight
                    class="size-3.5 text-muted-foreground/20 group-hover:text-primary/50 transition-colors duration-200" />
                </div>
              </div>
            </div>
          </section>

          <!-- Activity stream -->
          <section class="lg:col-span-2 h-[500px]">
            <ActivityStream />
          </section>
        </div>

  </main>
  </div>
</template>
