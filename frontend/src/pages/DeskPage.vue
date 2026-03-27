<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useWorkspaceStore } from '@/stores/workspace'
import { workspaceApi } from '@/core/api/workspace'
import DeskTopBar from '@/components/desk/DeskTopBar.vue'
import AppCard from '@/components/desk/AppCard.vue'
import GlobalSearch from '@/components/desk/GlobalSearch.vue'
import { Spinner } from '@/components/ui/spinner'
import { Plus, Clock, LayoutGrid } from 'lucide-vue-next'

const auth = useAuthStore()
const wsStore = useWorkspaceStore()
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
  <div class="min-h-screen bg-background">
    <DeskTopBar />

    <main class="max-w-5xl mx-auto px-6 py-10">

      <!-- Greeting + search -->
      <div class="mb-10">
        <h1 class="text-[28px] font-semibold text-foreground tracking-tight mb-1">
          {{ greeting }}
        </h1>
        <p class="text-sm text-muted-foreground mb-6">Що плануєте зробити сьогодні?</p>
        <GlobalSearch />
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

        <div v-else-if="wsStore.workspaces.length === 0 && !auth.user?.is_superadmin" class="text-center py-12 text-muted-foreground text-sm">
          Немає встановлених додатків
        </div>

        <div v-else class="flex flex-wrap gap-4">
          <AppCard
            v-for="ws in wsStore.workspaces"
            :key="ws.name"
            :workspace="ws"
            :counts="allCounts[ws.name]"
          />

          <!-- Add app (superadmin only) -->
          <button
            v-if="auth.user?.is_superadmin"
            class="w-44 h-44 flex flex-col items-center justify-center gap-2 border-2 border-dashed border-border rounded-xl text-muted-foreground hover:border-primary hover:text-primary hover:bg-accent/50 transition-all duration-200 group"
            @click="router.push('/studio/workspaces')"
          >
            <div class="w-9 h-9 rounded-full border-2 border-current flex items-center justify-center group-hover:scale-105 transition-transform duration-200">
              <Plus class="w-4 h-4" />
            </div>
            <span class="text-xs font-medium">Встановити додаток</span>
          </button>
        </div>
      </section>

      <!-- Recent documents -->
      <section v-if="recentDocs.length > 0">
        <div class="flex items-center gap-2 mb-4">
          <Clock class="w-4 h-4 text-muted-foreground" />
          <h2 class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Нещодавні документи</h2>
        </div>
        <div class="bg-card border border-border rounded-lg overflow-hidden">
          <div
            v-for="doc in recentDocs.slice(0, 5)"
            :key="doc.id"
            class="flex items-center gap-3 px-4 py-3 border-b border-border last:border-0 hover:bg-muted/40 cursor-pointer transition-colors"
            @click="router.push(`/${doc.workspace}/list/${doc.doctype}/${doc.id}`)"
          >
            <span
              v-if="findWorkspaceForDoc(doc)"
              class="text-[11px] px-1.5 py-0.5 rounded font-medium flex-shrink-0"
              :style="{
                backgroundColor: (findWorkspaceForDoc(doc)?.color ?? '#666') + '18',
                color: findWorkspaceForDoc(doc)?.color ?? '#666'
              }"
            >{{ findWorkspaceForDoc(doc)?.label }}</span>
            <span class="text-sm text-foreground flex-1 truncate">{{ doc.title }}</span>
            <span class="text-xs text-muted-foreground/60 flex-shrink-0 tabular-nums">{{ timeAgo(doc.ts) }}</span>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>
