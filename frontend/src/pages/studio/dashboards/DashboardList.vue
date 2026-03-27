<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { LayoutDashboard, Plus, Trash2, ExternalLink } from 'lucide-vue-next'
import { dashboardApi } from '@/core/api/dashboards'
import type { DashboardSummary } from '@/types'

const router = useRouter()
const dashboards = ref<DashboardSummary[]>([])
const loading = ref(true)
const creating = ref(false)

// Create dialog state
const showCreate = ref(false)
const newLabel = ref('')
const newDesc = ref('')

async function load() {
  loading.value = true
  try { dashboards.value = await dashboardApi.list() }
  finally { loading.value = false }
}

onMounted(load)

async function create() {
  if (!newLabel.value.trim()) return
  creating.value = true
  try {
    const d = await dashboardApi.create({ label: newLabel.value, description: newDesc.value })
    router.push({ name: 'studio-dashboard-builder', params: { name: d.name } })
  } finally { creating.value = false }
}

async function remove(d: DashboardSummary) {
  if (!confirm(`Видалити дашборд «${d.label}»?`)) return
  await dashboardApi.delete(d.name)
  dashboards.value = dashboards.value.filter(x => x.name !== d.name)
}
</script>

<template>
  <div class="p-8 max-w-4xl mx-auto">
    <!-- Header -->
    <div class="flex items-center justify-between mb-8">
      <div class="flex items-center gap-3">
        <LayoutDashboard class="w-6 h-6 text-primary" />
        <div>
          <h1 class="text-xl font-bold">Дашборди</h1>
          <p class="text-sm text-muted-foreground">Інформаційні панелі з KPI і графіками</p>
        </div>
      </div>
      <button
        class="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        @click="showCreate = true">
        <Plus class="w-4 h-4" /> Новий дашборд
      </button>
    </div>

    <!-- List skeleton -->
    <div v-if="loading" class="grid grid-cols-2 gap-4">
      <div v-for="i in 4" :key="i" class="h-32 bg-muted animate-pulse rounded-xl" />
    </div>

    <!-- Empty -->
    <div v-else-if="!dashboards.length" class="text-center py-20 text-muted-foreground">
      <LayoutDashboard class="w-12 h-12 mx-auto mb-3 opacity-30" />
      <p class="text-sm">Дашбордів ще немає</p>
    </div>

    <!-- Grid -->
    <div v-else class="grid grid-cols-2 gap-4">
      <div
        v-for="d in dashboards" :key="d.name"
        class="group bg-card border rounded-xl p-5 hover:shadow-md transition-shadow cursor-pointer"
        @click="router.push({ name: 'studio-dashboard-builder', params: { name: d.name } })"
      >
        <div class="flex items-start justify-between mb-3">
          <div class="p-2 bg-primary/10 rounded-lg">
            <LayoutDashboard class="w-5 h-5 text-primary" />
          </div>
          <div class="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity" @click.stop>
            <button
              class="p-1.5 rounded-md hover:bg-muted transition-colors"
              @click.stop="router.push({ name: 'studio-dashboard-builder', params: { name: d.name } })">
              <ExternalLink class="w-3.5 h-3.5" />
            </button>
            <button
              class="p-1.5 rounded-md hover:bg-destructive hover:text-destructive-foreground transition-colors"
              @click.stop="remove(d)">
              <Trash2 class="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
        <h3 class="font-semibold text-sm mb-1">{{ d.label }}</h3>
        <p v-if="d.description" class="text-xs text-muted-foreground line-clamp-2">{{ d.description }}</p>
        <div class="mt-3 flex items-center gap-2">
          <span :class="['text-xs px-2 py-0.5 rounded-full', d.is_published ? 'bg-emerald-100 text-emerald-700' : 'bg-muted text-muted-foreground']">
            {{ d.is_published ? 'Опублікований' : 'Чернетка' }}
          </span>
          <span v-if="d.workspace" class="text-xs text-muted-foreground">· {{ d.workspace }}</span>
        </div>
      </div>
    </div>

    <!-- Create dialog -->
    <Teleport to="body">
      <div v-if="showCreate" class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
        <div class="bg-card rounded-xl shadow-xl w-full max-w-md p-6" @click.stop>
          <h2 class="font-semibold mb-4">Новий дашборд</h2>
          <div class="space-y-3">
            <input
              v-model="newLabel" autofocus
              class="w-full h-10 px-3 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
              placeholder="Назва дашборду"
              @keydown.enter="create"
            />
            <textarea
              v-model="newDesc" rows="2"
              class="w-full px-3 py-2 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
              placeholder="Опис (необов'язково)"
            />
          </div>
          <div class="flex gap-2 mt-4">
            <button
              class="flex-1 h-10 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
              :disabled="creating || !newLabel.trim()"
              @click="create">
              {{ creating ? 'Створення…' : 'Створити' }}
            </button>
            <button
              class="h-10 px-4 rounded-lg border text-sm hover:bg-muted transition-colors"
              @click="showCreate = false; newLabel = ''; newDesc = ''">
              Скасувати
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
