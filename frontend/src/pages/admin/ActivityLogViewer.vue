<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useDocTypeStore } from '@/stores/doctype'
import api from '@/core/api/client'
import {
  Search, RefreshCcw, Plus, FileText, Trash2, Send,
  Share2, MessageSquare, GitBranch, ChevronLeft, ChevronRight,
  Filter, X,
} from 'lucide-vue-next'

interface ActivityEntry {
  id: string
  doctype: string
  doc_id: string
  action: string
  user: string
  details: unknown
  created_at: string | null
}

interface Meta { total: number; page: number; per_page: number; pages: number }

const router = useRouter()
const dtStore = useDocTypeStore()
dtStore.loadAll()

// ── Filters ──────────────────────────────────────────────────────────────────
const filters = reactive({
  doctype: '',
  user: '',
  action: '',
  date_from: '',
  date_to: '',
})
const page = ref(1)
const PER_PAGE = 50

const ACTIONS = ['Create', 'Update', 'Delete', 'Submit', 'Cancel', 'Share', 'Comment', 'Workflow']

// ── Data ──────────────────────────────────────────────────────────────────────
const entries = ref<ActivityEntry[]>([])
const meta = ref<Meta>({ total: 0, page: 1, per_page: PER_PAGE, pages: 0 })
const loading = ref(false)
const error = ref('')

async function fetchData() {
  loading.value = true
  error.value = ''
  try {
    const params: Record<string, string | number> = { limit: PER_PAGE, page: page.value }
    if (filters.doctype) params.doctype = filters.doctype
    if (filters.user)    params.user    = filters.user
    if (filters.action)  params.action  = filters.action
    if (filters.date_from) params.date_from = filters.date_from
    if (filters.date_to)   params.date_to   = filters.date_to

    const res = await api.get('/api/v1/activity/', { params })
    entries.value = res.data.data
    meta.value    = res.data.meta
  } catch (e: unknown) {
    error.value = (e as Error).message ?? 'Помилка завантаження'
  } finally {
    loading.value = false
  }
}

// Reset to page 1 when filters change
watch(filters, () => { page.value = 1 })
watch([filters, page], fetchData, { immediate: true, deep: true })

function clearFilters() {
  filters.doctype = ''
  filters.user = ''
  filters.action = ''
  filters.date_from = ''
  filters.date_to = ''
  page.value = 1
}

const hasFilters = computed(() =>
  filters.doctype || filters.user || filters.action || filters.date_from || filters.date_to
)

// ── Navigation ────────────────────────────────────────────────────────────────
function goToDoc(entry: ActivityEntry) {
  router.push(`/grunt/list/${entry.doctype}/${entry.doc_id}`)
}

// ── Formatting ────────────────────────────────────────────────────────────────
function getActionIcon(action: string) {
  switch (action?.toLowerCase()) {
    case 'create':   return Plus
    case 'update':   return RefreshCcw
    case 'delete':   return Trash2
    case 'submit':   return Send
    case 'share':    return Share2
    case 'comment':  return MessageSquare
    case 'workflow': return GitBranch
    default:         return FileText
  }
}

function getActionColor(action: string): string {
  switch (action?.toLowerCase()) {
    case 'create':   return 'text-emerald-600 bg-emerald-500/10 border-emerald-200'
    case 'update':   return 'text-amber-600 bg-amber-500/10 border-amber-200'
    case 'delete':   return 'text-rose-600 bg-rose-500/10 border-rose-200'
    case 'submit':   return 'text-blue-600 bg-blue-500/10 border-blue-200'
    case 'workflow': return 'text-violet-600 bg-violet-500/10 border-violet-200'
    default:         return 'text-muted-foreground bg-muted border-border'
  }
}

function getActionLabel(action: string): string {
  const map: Record<string, string> = {
    create: 'Створення', update: 'Оновлення', delete: 'Видалення',
    submit: 'Фіксація', cancel: 'Скасування',
    share: 'Поширення', comment: 'Коментар', workflow: 'Workflow',
  }
  return map[action?.toLowerCase()] ?? action
}

function formatTime(val: string | null): string {
  if (!val) return '—'
  const d = new Date(val)
  return d.toLocaleString('uk-UA', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}
</script>

<template>
  <div class="flex flex-col h-full bg-background">

    <!-- Header -->
    <div class="px-6 py-5 border-b flex items-center justify-between gap-4 shrink-0">
      <div>
        <h1 class="text-lg font-semibold">Журнал активності</h1>
        <p class="text-sm text-muted-foreground mt-0.5">
          Перегляд усіх дій в системі
          <span v-if="!loading" class="ml-1 text-xs">({{ meta.total }} записів)</span>
        </p>
      </div>
      <button
        class="flex items-center gap-1.5 px-3 py-1.5 text-sm border rounded-lg hover:bg-muted transition-colors"
        :class="loading ? 'opacity-50 pointer-events-none' : ''"
        @click="fetchData"
      >
        <RefreshCcw class="size-3.5" :class="loading ? 'animate-spin' : ''" />
        Оновити
      </button>
    </div>

    <!-- Filter bar -->
    <div class="px-6 py-3 border-b bg-muted/30 shrink-0 flex flex-wrap items-center gap-3">
      <Filter class="size-4 text-muted-foreground shrink-0" />

      <!-- DocType -->
      <select
        v-model="filters.doctype"
        class="h-8 px-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 min-w-[140px]"
      >
        <option value="">Всі DocType</option>
        <option v-for="dt in dtStore.doctypes.filter(d => !d.is_child)" :key="dt.name" :value="dt.name">
          {{ dt.label }}
        </option>
      </select>

      <!-- Action -->
      <select
        v-model="filters.action"
        class="h-8 px-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
      >
        <option value="">Всі дії</option>
        <option v-for="a in ACTIONS" :key="a" :value="a">{{ getActionLabel(a) }}</option>
      </select>

      <!-- User -->
      <div class="relative">
        <Search class="absolute left-2 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
        <input
          v-model="filters.user"
          placeholder="Користувач..."
          class="h-8 pl-7 pr-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 w-44"
        />
      </div>

      <!-- Date range -->
      <input
        v-model="filters.date_from"
        type="date"
        class="h-8 px-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
      />
      <span class="text-xs text-muted-foreground">—</span>
      <input
        v-model="filters.date_to"
        type="date"
        class="h-8 px-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
      />

      <!-- Clear -->
      <button
        v-if="hasFilters"
        class="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors ml-auto"
        @click="clearFilters"
      >
        <X class="size-3.5" />
        Скинути
      </button>
    </div>

    <!-- Table -->
    <div class="flex-1 overflow-auto">
      <!-- Loading skeleton -->
      <div v-if="loading && entries.length === 0" class="p-6 flex flex-col gap-2">
        <div v-for="i in 8" :key="i" class="h-12 bg-muted animate-pulse rounded-lg" />
      </div>

      <!-- Error -->
      <div v-else-if="error" class="flex items-center justify-center h-full text-sm text-destructive">
        {{ error }}
      </div>

      <!-- Empty -->
      <div v-else-if="entries.length === 0"
        class="flex flex-col items-center justify-center h-full text-muted-foreground gap-2">
        <FileText class="size-8 opacity-30" />
        <p class="text-sm">Записів не знайдено</p>
      </div>

      <!-- Entries table -->
      <table v-else class="w-full text-sm">
        <thead class="sticky top-0 bg-background border-b z-10">
          <tr class="text-left text-xs text-muted-foreground font-medium">
            <th class="px-6 py-3 w-8"></th>
            <th class="px-3 py-3">Дія</th>
            <th class="px-3 py-3">DocType</th>
            <th class="px-3 py-3">Документ</th>
            <th class="px-3 py-3">Користувач</th>
            <th class="px-6 py-3 text-right">Час</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-border/50">
          <tr
            v-for="entry in entries"
            :key="entry.id"
            class="hover:bg-muted/30 transition-colors cursor-pointer group"
            @click="goToDoc(entry)"
          >
            <!-- Action icon -->
            <td class="px-6 py-3">
              <div :class="['size-7 rounded-md border flex items-center justify-center', getActionColor(entry.action)]">
                <component :is="getActionIcon(entry.action)" class="size-3.5" />
              </div>
            </td>

            <!-- Action label -->
            <td class="px-3 py-3">
              <span :class="['inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border', getActionColor(entry.action)]">
                {{ getActionLabel(entry.action) }}
              </span>
            </td>

            <!-- DocType -->
            <td class="px-3 py-3 text-muted-foreground">{{ entry.doctype }}</td>

            <!-- Doc ID -->
            <td class="px-3 py-3">
              <span class="font-medium text-foreground group-hover:text-primary transition-colors truncate max-w-[200px] block">
                {{ entry.doc_id }}
              </span>
            </td>

            <!-- User -->
            <td class="px-3 py-3 text-muted-foreground truncate max-w-[160px]">{{ entry.user }}</td>

            <!-- Time -->
            <td class="px-6 py-3 text-right text-muted-foreground tabular-nums text-xs">
              {{ formatTime(entry.created_at) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div v-if="meta.pages > 1" class="px-6 py-3 border-t bg-muted/30 shrink-0 flex items-center justify-between">
      <span class="text-xs text-muted-foreground">
        {{ (meta.page - 1) * meta.per_page + 1 }}–{{ Math.min(meta.page * meta.per_page, meta.total) }}
        з {{ meta.total }}
      </span>
      <div class="flex items-center gap-1">
        <button
          :disabled="page <= 1"
          class="p-1.5 rounded-md border hover:bg-muted transition-colors disabled:opacity-40 disabled:pointer-events-none"
          @click="page--"
        >
          <ChevronLeft class="size-4" />
        </button>
        <span class="px-3 text-sm font-medium">{{ page }} / {{ meta.pages }}</span>
        <button
          :disabled="page >= meta.pages"
          class="p-1.5 rounded-md border hover:bg-muted transition-colors disabled:opacity-40 disabled:pointer-events-none"
          @click="page++"
        >
          <ChevronRight class="size-4" />
        </button>
      </div>
    </div>

  </div>
</template>
