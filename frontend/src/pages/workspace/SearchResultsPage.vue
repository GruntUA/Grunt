<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useWorkspaceStore } from '@/stores/workspace'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/core/composables/useToast'
import client from '@/core/api/client'
import { Button } from '@/components/ui/button'
import { Search, FileText, Loader2, RefreshCw, X } from '@lucide/vue'

const props = defineProps<{ workspaceName?: string }>()

const route = useRoute()
const router = useRouter()
const wsStore = useWorkspaceStore()
const auth = useAuthStore()
const toast = useToast()

// ── State ─────────────────────────────────────────────────────────────────

interface SearchResult {
  idx_id: string
  doctype: string
  doc_id: string
  doc_name: string
  title: string
  module: string
}

const q = ref(String(route.query.q ?? ''))
const inputQ = ref(q.value)
const results = ref<SearchResult[]>([])
const isLoading = ref(false)
const isReindexing = ref(false)
const activeDoctype = ref<string | null>(null)

// ── Search ────────────────────────────────────────────────────────────────

async function runSearch() {
  const query = q.value.trim()
  if (query.length < 2) { results.value = []; return }

  isLoading.value = true
  try {
    const res = await client.get('/api/v1/search', { params: { q: query, limit: 100 } })
    results.value = (res.data ?? []) as SearchResult[]
    activeDoctype.value = null
  } catch {
    toast.error('Помилка пошуку')
  } finally {
    isLoading.value = false
  }
}

let debounceTimer: ReturnType<typeof setTimeout>
watch(inputQ, (val) => {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    q.value = val
    router.replace({ query: { ...route.query, q: val || undefined } })
  }, 350)
})

watch(q, runSearch)

onMounted(async () => {
  if (wsStore.workspaces.length === 0) await wsStore.loadAll()
  if (q.value) runSearch()
})

// ── Grouping ──────────────────────────────────────────────────────────────

const filtered = computed(() =>
  activeDoctype.value
    ? results.value.filter(r => r.doctype === activeDoctype.value)
    : results.value
)

const groups = computed(() => {
  const m = new Map<string, SearchResult[]>()
  for (const r of filtered.value) {
    if (!m.has(r.doctype)) m.set(r.doctype, [])
    m.get(r.doctype)!.push(r)
  }
  return [...m.entries()].map(([doctype, items]) => ({ doctype, items }))
})

const doctypeChips = computed(() => {
  const m = new Map<string, number>()
  for (const r of results.value) m.set(r.doctype, (m.get(r.doctype) ?? 0) + 1)
  return [...m.entries()].map(([doctype, count]) => ({ doctype, count })).sort((a, b) => b.count - a.count)
})

// ── Navigation ────────────────────────────────────────────────────────────

function navigateToDoc(r: SearchResult) {
  const ws = wsStore.workspaces.find(w => w.items?.some(i => i.link_to === r.doctype))
  const workspace = ws?.name ?? props.workspaceName ?? 'grunt'
  router.push(`/${workspace}/list/${r.doctype}/${r.doc_id}`)
}

// ── Reindex ───────────────────────────────────────────────────────────────

async function reindex() {
  isReindexing.value = true
  try {
    const res = await client.post('/api/v1/search/reindex')
    toast.success(`Індекс перебудовано: ${res.data.indexed} документів`)
    await runSearch()
  } catch {
    toast.error('Помилка перебудови індексу')
  } finally {
    isReindexing.value = false
  }
}
</script>

<template>
  <div class="flex flex-col gap-6 p-6 max-w-4xl mx-auto w-full">
    <!-- Header + search input -->
    <div class="flex flex-col gap-3">
      <div class="flex items-center justify-between">
        <h2 class="text-2xl font-bold text-foreground">Пошук</h2>
        <Button
          v-if="auth.user?.is_superadmin"
          variant="outline"
          size="sm"
          class="h-8 text-xs text-foreground"
          :disabled="isReindexing"
          @click="reindex"
        >
          <Loader2 v-if="isReindexing" class="size-3.5 mr-1.5 animate-spin" />
          <RefreshCw v-else class="size-3.5 mr-1.5" />
          Перебудувати індекс
        </Button>
      </div>

      <!-- Search box -->
      <div class="relative">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" />
        <input
          v-model="inputQ"
          placeholder="Пошук по всіх документах..."
          class="w-full h-11 pl-10 pr-4 rounded-lg border border-input bg-background text-base text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          autofocus
        />
        <button v-if="inputQ" class="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground" @click="inputQ = ''">
          <X class="size-4" />
        </button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="isLoading" class="flex items-center justify-center py-16 gap-3 text-muted-foreground">
      <Loader2 class="size-5 animate-spin" />
      <span class="text-sm">Шукаємо...</span>
    </div>

    <!-- Empty state -->
    <div v-else-if="q.length >= 2 && !results.length" class="flex flex-col items-center gap-2 py-16 text-center">
      <Search class="size-10 text-muted-foreground/30" />
      <p class="text-sm text-muted-foreground">Нічого не знайдено для <b>"{{ q }}"</b></p>
      <p class="text-xs text-muted-foreground/60">Спробуйте інші ключові слова або <button class="underline hover:text-foreground" @click="reindex">перебудуйте індекс</button></p>
    </div>

    <div v-else-if="q.length < 2 && !isLoading" class="flex flex-col items-center gap-2 py-16 text-center text-muted-foreground">
      <Search class="size-10 opacity-20" />
      <p class="text-sm">Введіть мінімум 2 символи для пошуку</p>
    </div>

    <template v-else-if="results.length">
      <!-- Summary + DocType filter chips -->
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-sm text-muted-foreground">
          {{ results.length }} {{ results.length === 1 ? 'результат' : 'результатів' }}
        </span>
        <button
          class="text-xs px-2.5 py-1 rounded-full border transition-colors"
          :class="activeDoctype === null
            ? 'border-primary bg-primary/10 text-primary'
            : 'border-border text-muted-foreground hover:border-primary/50'"
          @click="activeDoctype = null"
        >
          Всі
        </button>
        <button
          v-for="chip in doctypeChips"
          :key="chip.doctype"
          class="text-xs px-2.5 py-1 rounded-full border transition-colors"
          :class="activeDoctype === chip.doctype
            ? 'border-primary bg-primary/10 text-primary'
            : 'border-border text-muted-foreground hover:border-primary/50'"
          @click="activeDoctype = activeDoctype === chip.doctype ? null : chip.doctype"
        >
          {{ chip.doctype }}
          <span class="ml-1 opacity-60">{{ chip.count }}</span>
        </button>
      </div>

      <!-- Results grouped by DocType -->
      <div class="space-y-6">
        <div v-for="group in groups" :key="group.doctype">
          <h3 class="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-2">
            <FileText class="size-3.5" />
            {{ group.doctype }}
            <span class="font-normal opacity-60">({{ group.items.length }})</span>
          </h3>

          <div class="rounded-lg border border-border divide-y divide-border overflow-hidden">
            <button
              v-for="item in group.items"
              :key="item.idx_id"
              class="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-muted/40 transition-colors group"
              @click="navigateToDoc(item)"
            >
              <div class="size-8 rounded-md bg-primary/10 flex items-center justify-center shrink-0">
                <FileText class="size-4 text-primary" />
              </div>
              <div class="flex-1 min-w-0">
                <p class="text-sm font-semibold text-foreground group-hover:text-primary transition-colors truncate">
                  {{ item.title || item.doc_name }}
                </p>
                <p v-if="item.title && item.title !== item.doc_name" class="text-xs text-muted-foreground truncate">
                  {{ item.doc_name }}
                </p>
              </div>
              <span class="text-xs text-muted-foreground/60 shrink-0 hidden sm:block">{{ item.module }}</span>
            </button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
