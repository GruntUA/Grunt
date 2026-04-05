<script setup lang="ts">
/**
 * ProfilerPanel — dev-only SQL query profiler overlay.
 *
 * Toggle:  Ctrl+Shift+P
 * Shows:   per-request breakdown + global slow-query list + aggregate stats
 *
 * Only rendered when import.meta.env.DEV is true.
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { X, RefreshCw, Trash2, ChevronDown, ChevronRight, AlertTriangle, Zap, Clock, Database } from 'lucide-vue-next'
import { ScrollArea } from '@/components/ui/scroll-area'
import client from '@/core/api/client'

// ── Types ──────────────────────────────────────────────────────────────────

interface QueryRecord {
  sql: string
  duration_ms: number
  param_count: number
  slow: boolean
  request_id: string | null
}

interface RequestProfile {
  request_id: string
  method: string
  path: string
  status_code: number
  duration_ms: number
  query_count: number
  slow_query_count: number
  total_query_ms: number
  queries: QueryRecord[]
}

interface Stats {
  request_count: number
  slow_query_count: number
  avg_duration_ms: number
  p95_duration_ms: number
}

// ── State ──────────────────────────────────────────────────────────────────

const open   = ref(false)
const tab    = ref<'requests' | 'slow'>('requests')
const loading = ref(false)

const requests   = ref<RequestProfile[]>([])
const slowQueries = ref<QueryRecord[]>([])
const stats      = ref<Stats | null>(null)
const expanded   = ref<Set<string>>(new Set())

// ── Keyboard shortcut ──────────────────────────────────────────────────────

function onKeyDown(e: KeyboardEvent) {
  if (e.ctrlKey && e.shiftKey && e.key === 'P') {
    e.preventDefault()
    open.value = !open.value
    if (open.value) loadAll()
  }
}

onMounted(() => window.addEventListener('keydown', onKeyDown))
onUnmounted(() => window.removeEventListener('keydown', onKeyDown))

// ── Data loading ───────────────────────────────────────────────────────────

async function loadAll() {
  loading.value = true
  try {
    const [req, slow, st] = await Promise.all([
      client.get('/api/v1/dev/profiler/requests?limit=50'),
      client.get('/api/v1/dev/profiler/slow-queries?limit=100'),
      client.get('/api/v1/dev/profiler/stats'),
    ])
    requests.value   = req.data.data
    slowQueries.value = slow.data.data
    stats.value      = st.data.data
  } catch {
    // server may not be in debug mode
  } finally {
    loading.value = false
  }
}

async function clearAll() {
  await client.delete('/api/v1/dev/profiler/clear')
  requests.value   = []
  slowQueries.value = []
  stats.value      = null
}

// ── Helpers ────────────────────────────────────────────────────────────────

function toggleExpand(id: string) {
  expanded.value.has(id) ? expanded.value.delete(id) : expanded.value.add(id)
}

function methodColor(method: string) {
  return {
    GET: 'text-blue-500',
    POST: 'text-green-500',
    PUT: 'text-yellow-500',
    PATCH: 'text-orange-500',
    DELETE: 'text-red-500',
  }[method] ?? 'text-muted-foreground'
}

function statusColor(code: number) {
  if (code < 300) return 'text-green-500'
  if (code < 400) return 'text-yellow-500'
  return 'text-red-500'
}

function durationColor(ms: number) {
  if (ms < 100) return 'text-green-500'
  if (ms < 500) return 'text-yellow-500'
  return 'text-red-500'
}

const slowCount = computed(() => requests.value.reduce((s, r) => s + r.slow_query_count, 0))
</script>

<template>
  <!-- Trigger badge — bottom-left corner -->
  <button
    class="fixed bottom-4 left-4 z-[300] flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-zinc-900 text-zinc-100 text-xs font-mono shadow-lg hover:bg-zinc-800 transition-colors border border-zinc-700"
    :class="slowCount > 0 ? 'border-amber-500/60' : ''"
    @click="open = !open; if (open) loadAll()"
    title="Profiler (Ctrl+Shift+P)"
  >
    <Database class="w-3.5 h-3.5" :class="slowCount > 0 ? 'text-amber-400' : 'text-zinc-400'" />
    <span>SQL</span>
    <span v-if="stats" class="text-zinc-400">{{ stats.request_count }}req</span>
    <span v-if="slowCount > 0" class="text-amber-400 font-bold">{{ slowCount }}⚠</span>
  </button>

  <!-- Panel -->
  <Transition
    enter-active-class="transition-all duration-200 ease-out"
    enter-from-class="opacity-0 translate-y-2"
    enter-to-class="opacity-100 translate-y-0"
    leave-active-class="transition-all duration-150 ease-in"
    leave-from-class="opacity-100"
    leave-to-class="opacity-0"
  >
    <div
      v-if="open"
      class="fixed bottom-14 left-4 z-[299] w-[680px] max-w-[calc(100vw-2rem)] bg-zinc-950 border border-zinc-800 rounded-xl shadow-2xl font-mono text-xs text-zinc-200 overflow-hidden flex flex-col"
      style="max-height: 70vh"
    >
      <!-- Header -->
      <div class="flex items-center gap-3 px-4 py-2.5 border-b border-zinc-800 bg-zinc-900 shrink-0">
        <Database class="w-4 h-4 text-zinc-400" />
        <span class="font-semibold text-zinc-100 text-sm">SQL Profiler</span>

        <!-- Stats pills -->
        <div v-if="stats" class="flex items-center gap-2 ml-2">
          <span class="flex items-center gap-1 px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-400">
            <Zap class="w-3 h-3" />{{ stats.request_count }} req
          </span>
          <span class="flex items-center gap-1 px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-400">
            <Clock class="w-3 h-3" />avg {{ stats.avg_duration_ms }}ms / p95 {{ stats.p95_duration_ms }}ms
          </span>
          <span
            v-if="stats.slow_query_count > 0"
            class="flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-950 text-amber-400"
          >
            <AlertTriangle class="w-3 h-3" />{{ stats.slow_query_count }} slow
          </span>
        </div>

        <div class="ml-auto flex items-center gap-1">
          <button class="p-1.5 rounded hover:bg-zinc-800 transition-colors text-zinc-400 hover:text-zinc-200"
            :class="loading ? 'animate-spin' : ''" @click="loadAll" title="Refresh">
            <RefreshCw class="w-3.5 h-3.5" />
          </button>
          <button class="p-1.5 rounded hover:bg-zinc-800 transition-colors text-zinc-400 hover:text-red-400"
            @click="clearAll" title="Clear">
            <Trash2 class="w-3.5 h-3.5" />
          </button>
          <button class="p-1.5 rounded hover:bg-zinc-800 transition-colors text-zinc-400 hover:text-zinc-200"
            @click="open = false">
            <X class="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <!-- Tabs -->
      <div class="flex border-b border-zinc-800 shrink-0 bg-zinc-900">
        <button
          v-for="t in (['requests', 'slow'] as const)"
          :key="t"
          class="px-4 py-2 text-xs transition-colors border-b-2"
          :class="tab === t
            ? 'text-zinc-100 border-primary'
            : 'text-zinc-500 border-transparent hover:text-zinc-300'"
          @click="tab = t"
        >
          {{ t === 'requests' ? `Requests (${requests.length})` : `Slow queries (${slowQueries.length})` }}
        </button>
      </div>

      <!-- Requests tab -->
      <ScrollArea v-if="tab === 'requests'" class="flex-1">
        <div v-if="requests.length === 0" class="py-8 text-center text-zinc-600">
          Немає даних. Зробіть кілька запитів і натисніть ↺
        </div>
        <div v-for="req in requests" :key="req.request_id" class="border-b border-zinc-800/60 last:border-0">
          <!-- Request row -->
          <button
            class="w-full flex items-center gap-2 px-4 py-2 hover:bg-zinc-900 transition-colors text-left"
            @click="toggleExpand(req.request_id)"
          >
            <component :is="expanded.has(req.request_id) ? ChevronDown : ChevronRight"
              class="w-3 h-3 text-zinc-600 shrink-0" />
            <span class="w-14 font-bold shrink-0" :class="methodColor(req.method)">{{ req.method }}</span>
            <span class="flex-1 truncate text-zinc-300">{{ req.path }}</span>
            <span class="shrink-0 w-10 text-right" :class="statusColor(req.status_code)">{{ req.status_code }}</span>
            <span class="shrink-0 w-20 text-right" :class="durationColor(req.duration_ms)">
              {{ req.duration_ms.toFixed(1) }}ms
            </span>
            <span class="shrink-0 w-16 text-right text-zinc-500">
              {{ req.query_count }}q / {{ req.total_query_ms.toFixed(0) }}ms
            </span>
            <span v-if="req.slow_query_count > 0" class="shrink-0 text-amber-400 font-bold">
              ⚠ {{ req.slow_query_count }}
            </span>
          </button>

          <!-- Expanded queries -->
          <div v-if="expanded.has(req.request_id)" class="bg-zinc-900/50 border-t border-zinc-800/40">
            <div
              v-for="(q, i) in req.queries"
              :key="i"
              class="flex items-start gap-2 px-8 py-1.5 border-b border-zinc-800/30 last:border-0"
              :class="q.slow ? 'bg-amber-950/20' : ''"
            >
              <span class="shrink-0 w-16 text-right mt-px" :class="durationColor(q.duration_ms)">
                {{ q.duration_ms.toFixed(2) }}ms
              </span>
              <span
                v-if="q.slow"
                class="shrink-0 text-amber-400 text-[10px] mt-px leading-none px-1 py-0.5 rounded bg-amber-950/50"
              >SLOW</span>
              <span class="flex-1 text-zinc-400 break-all leading-relaxed">{{ q.sql }}</span>
            </div>
            <div v-if="req.queries.length === 0" class="px-8 py-2 text-zinc-600">
              Запитів не зафіксовано
            </div>
          </div>
        </div>
      </ScrollArea>

      <!-- Slow queries tab -->
      <ScrollArea v-else class="flex-1">
        <div v-if="slowQueries.length === 0" class="py-8 text-center text-zinc-600">
          Повільних запитів не знайдено
        </div>
        <div
          v-for="(q, i) in slowQueries"
          :key="i"
          class="flex items-start gap-2 px-4 py-2.5 border-b border-zinc-800/60 last:border-0 bg-amber-950/10"
        >
          <AlertTriangle class="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
          <span class="shrink-0 w-20 text-amber-400 font-bold mt-px text-right">
            {{ q.duration_ms.toFixed(2) }}ms
          </span>
          <span class="flex-1 text-zinc-300 break-all leading-relaxed">{{ q.sql }}</span>
          <span v-if="q.request_id" class="shrink-0 text-zinc-600 text-[10px] mt-px truncate max-w-24">
            {{ q.request_id.slice(0, 8) }}
          </span>
        </div>
      </ScrollArea>
    </div>
  </Transition>
</template>
