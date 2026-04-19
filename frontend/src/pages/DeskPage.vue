<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useWorkspaceStore } from '@/stores/workspace'
import { useUIStore } from '@/stores/ui'
import { workspaceApi } from '@/core/api/workspace'
import AppSidebar from '@/components/AppSidebar.vue'
import AppCard from '@/components/desk/AppCard.vue'
import ActivityStream from '@/components/dashboard/ActivityStream.vue'
import { Spinner } from '@/components/ui/spinner'
import { SidebarProvider, SidebarInset, SidebarTrigger } from '@/components/ui/sidebar'
import { Clock, LayoutGrid, Search } from '@lucide/vue'

const auth = useAuthStore()
const wsStore = useWorkspaceStore()
const uiStore = useUIStore()
const router = useRouter()

const allCounts = ref<Record<string, Record<string, number>>>({})

interface RecentDoc {
  workspace: string
  doctype: string
  id: string
  title: string
  ts: number
}

const recentDocs = ref<RecentDoc[]>([])

const greeting = computed(() => {
  const hour = new Date().getHours()
  const name = auth.user?.full_name?.split(' ')[0] ?? 'користувач'
  if (hour < 12) return `Доброго ранку, ${name}`
  if (hour < 18) return `Доброго дня, ${name}`
  return `Доброго вечора, ${name}`
})

onMounted(async () => {
  await wsStore.loadAll()

  for (const ws of wsStore.workspaces) {
    try {
      allCounts.value[ws.name] = await workspaceApi.getCounts(ws.name)
    } catch {
      allCounts.value[ws.name] = {}
    }
  }

  try {
    const saved = localStorage.getItem('grunt_recent_docs')
    if (saved) recentDocs.value = JSON.parse(saved)
  } catch {
    // ignore
  }
})

function timeAgo(ts: number): string {
  const diff = Date.now() - ts
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return 'щойно'
  if (minutes < 60) return `${minutes} хв тому`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} год тому`
  const days = Math.floor(hours / 24)
  return `${days} дн тому`
}

function findWorkspaceForDoc(doc: RecentDoc) {
  return wsStore.workspaces.find(w => w.name === doc.workspace)
}
</script>

<template>
  <SidebarProvider>
    <AppSidebar />
    <SidebarInset class="overflow-y-auto">

    <main class="max-w-5xl mx-auto px-6 py-6 md:py-10">

      <!-- Greeting + search -->
      <div class="mb-10">
        <div class="flex items-center gap-3 mb-4 md:mb-1">
          <SidebarTrigger class="md:hidden shrink-0 -ml-3" />
          <h1 class="text-[28px] font-semibold text-foreground tracking-tight leading-none">
            {{ greeting }}
          </h1>
        </div>
        <p class="text-sm text-muted-foreground mb-6">Що плануєте зробити сьогодні?</p>
        <div class="relative max-w-xl group cursor-pointer" @click="uiStore.openCommandPalette">
          <Search
            class="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground/60 transition-colors group-hover:text-primary" />
          <div
            class="w-full pl-12 pr-16 py-3.5 text-sm bg-card border border-border/60 rounded-2xl shadow-sm transition-all group-hover:border-primary/30 group-hover:ring-4 group-hover:ring-primary/5 text-muted-foreground/50">
            Шукайте документи, додатки або дії... (Ctrl+K)
          </div>
          <kbd
            class="absolute right-4 top-1/2 -translate-y-1/2 hidden sm:inline-flex items-center gap-1 px-2 py-1 rounded-md bg-muted text-[10px] font-bold text-muted-foreground border shadow-sm">
            <span>&#8984;</span>K
          </kbd>
        </div>
      </div>

      <!-- Workspace cards -->
      <section class="mb-10">
        <div class="flex items-center gap-2 mb-4">
          <LayoutGrid class="w-4 h-4 text-muted-foreground" />
          <h2 class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Ваші додатки</h2>
        </div>

        <div v-if="wsStore.loading" class="flex justify-center py-12">
          <Spinner size="lg" />
        </div>

        <div v-else-if="wsStore.workspaces.length === 0 && !auth.user?.is_superadmin"
          class="text-center py-12 text-muted-foreground text-sm">
          Немає встановлених додатків
        </div>

        <div v-else class="flex flex-wrap gap-4">
          <AppCard v-for="ws in wsStore.workspaces" :key="ws.name" :workspace="ws" :counts="allCounts[ws.name]" />

        </div>
      </section>

      <!-- Recent Activity & Documents -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">
        <!-- Recent documents (Left column) -->
        <section v-if="recentDocs.length > 0" class="lg:col-span-2">
          <div class="flex items-center gap-2 mb-4">
            <Clock class="w-4 h-4 text-muted-foreground" />
            <h2 class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Нещодавні документи</h2>
          </div>
          <div class="bg-card border border-border/60 rounded-xl overflow-hidden shadow-sm">
            <div v-for="doc in recentDocs.slice(0, 8)" :key="doc.id"
              class="flex items-center gap-3 px-4 py-3.5 border-b border-border/40 last:border-0 hover:bg-muted/40 cursor-pointer transition-colors group"
              @click="router.push(`/${doc.workspace}/list/${doc.doctype}/${doc.id}`)">
              <span v-if="findWorkspaceForDoc(doc)"
                class="text-[10px] px-2 py-0.5 rounded-full font-bold shrink-0 shadow-sm" :style="{
                  backgroundColor: (findWorkspaceForDoc(doc)?.color ?? '#666') + '20',
                  color: findWorkspaceForDoc(doc)?.color ?? '#666'
                }">{{ findWorkspaceForDoc(doc)?.label }}</span>
              <span
                class="text-sm text-foreground flex-1 truncate group-hover:text-primary transition-colors font-medium">{{
                doc.title }}</span>
              <span class="text-[10px] text-muted-foreground/60 shrink-0 tabular-nums font-mono">{{ timeAgo(doc.ts)
                }}</span>
            </div>
          </div>
        </section>

        <!-- Activity Stream (Right column) -->
        <section class="lg:col-span-1 h-[600px]">
          <ActivityStream />
        </section>
      </div>
    </main>
    </SidebarInset>
  </SidebarProvider>
</template>
