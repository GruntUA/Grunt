<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useWorkspaceStore } from '@/stores/workspace'
import { workspaceApi } from '@/core/api/workspace'
import DeskTopBar from '@/components/desk/DeskTopBar.vue'
import AppCard from '@/components/desk/AppCard.vue'
import GlobalSearch from '@/components/desk/GlobalSearch.vue'
import GSpinner from '@/components/ui/GSpinner.vue'

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

  // Load counts for each workspace
  for (const ws of wsStore.workspaces) {
    try {
      allCounts.value[ws.name] = await workspaceApi.getCounts(ws.name)
    } catch {
      allCounts.value[ws.name] = {}
    }
  }

  // Load recent docs from localStorage
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
  <div class="min-h-screen bg-[--grunt-surface-secondary]">
    <DeskTopBar />

    <main class="max-w-5xl mx-auto px-6 py-10">
      <!-- Greeting -->
      <h1 class="text-2xl font-semibold text-[--grunt-text-primary] mb-6">
        {{ greeting }} 👋
      </h1>

      <!-- Global search -->
      <div class="mb-10">
        <GlobalSearch />
      </div>

      <!-- Workspace cards -->
      <div class="mb-10">
        <h2 class="text-sm font-semibold text-[--grunt-text-secondary] uppercase tracking-wider mb-4">Ваші додатки</h2>

        <div v-if="wsStore.loading" class="flex justify-center py-8">
          <GSpinner size="lg" />
        </div>

        <div v-else class="flex flex-wrap gap-4">
          <AppCard
            v-for="ws in wsStore.workspaces"
            :key="ws.name"
            :workspace="ws"
            :counts="allCounts[ws.name]"
          />

          <!-- Add app button (superadmin only) -->
          <div
            v-if="auth.user?.is_superadmin"
            class="flex flex-col items-center justify-center border-2 border-dashed border-[--grunt-border] rounded-[--grunt-radius-lg] cursor-pointer hover:border-[--grunt-primary] hover:bg-[--grunt-surface] transition-all"
            :style="{ width: 'var(--grunt-app-card-w)', height: 'var(--grunt-app-card-h)' }"
            @click="router.push('/studio/workspaces')"
          >
            <span class="text-2xl text-[--grunt-text-muted] mb-1">+</span>
            <span class="text-xs text-[--grunt-text-muted]">Встановити додаток</span>
          </div>
        </div>
      </div>

      <!-- Recent documents -->
      <div v-if="recentDocs.length > 0">
        <h2 class="text-sm font-semibold text-[--grunt-text-secondary] uppercase tracking-wider mb-4">Нещодавні документи</h2>
        <div class="bg-[--grunt-surface] border border-[--grunt-border] rounded-[--grunt-radius-lg] overflow-hidden">
          <div
            v-for="doc in recentDocs.slice(0, 5)"
            :key="doc.id"
            class="flex items-center gap-3 px-4 py-3 border-b border-[--grunt-border] last:border-0 hover:bg-[--grunt-surface-secondary] cursor-pointer transition-colors"
            @click="router.push(`/${doc.workspace}/list/${doc.doctype}/${doc.id}`)"
          >
            <span
              v-if="findWorkspaceForDoc(doc)"
              class="text-xs px-2 py-0.5 rounded-full font-medium"
              :style="{
                backgroundColor: (findWorkspaceForDoc(doc)?.color ?? '#666') + '18',
                color: findWorkspaceForDoc(doc)?.color ?? '#666'
              }"
            >{{ findWorkspaceForDoc(doc)?.label }}</span>
            <span class="text-sm text-[--grunt-text-primary] flex-1">{{ doc.title }}</span>
            <span class="text-xs text-[--grunt-text-muted]">{{ timeAgo(doc.ts) }}</span>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>
