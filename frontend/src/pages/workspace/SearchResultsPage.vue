<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useWorkspaceStore } from '@/stores/workspace'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/core/composables/useToast'
import client from '@/core/api/client'
import { FileText } from '@lucide/vue'

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
  id: string
  name: string
  display_title: string
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
    const res = await client.get('/api/v1/method/grunt.api.v1.search.global_search', { params: { q: query, limit: 50 } })
    results.value = (res.data?.data ?? []) as SearchResult[]
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
  router.push(`/${workspace}/${r.doctype}/${r.id}`)
}

// ── Reindex ───────────────────────────────────────────────────────────────

async function reindex() {
  isReindexing.value = true
  try {
    const res = await client.post('/api/v1/method/grunt.api.v1.search.rebuild_index')
    toast.success(`Індекс перебудовано: ${res.data?.data?.indexed || 0} документів`)
    await runSearch()
  } catch {
    toast.error('Помилка перебудови індексу')
  } finally {
    isReindexing.value = false
  }
}
</script>

<template>
  <div class="flex flex-col gap-6 p-6 max-w-5xl mx-auto w-full">

    <!-- ── Header ── -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-foreground">Глобальний пошук</h1>
        <p class="text-sm text-muted-foreground mt-0.5">Пошук по всіх документах системи</p>
      </div>
      <Button
        v-if="auth.user?.is_superadmin"
        outlined
        size="small"
        :loading="isReindexing"
        icon="pi pi-refresh"
        label="Перебудувати індекс"
        @click="reindex"
      />
    </div>

    <!-- ── Search InputText ── -->
    <IconField>
      <InputIcon class="pi pi-search" />
      <InputText
        v-model="inputQ"
        placeholder="Введіть мінімум 2 символи для пошуку..."
        class="w-full"
        size="large"
        autofocus
      />
      <InputIcon v-if="inputQ" class="pi pi-times cursor-pointer" @click="inputQ = ''" />
    </IconField>

    <!-- ── Loading ── -->
    <div v-if="isLoading" class="flex flex-col gap-2">
      <ProgressBar mode="indeterminate" style="height: 3px" />
      <p class="text-sm text-muted-foreground text-center">Шукаємо...</p>
    </div>

    <!-- ── Too short ── -->
    <div v-else-if="q.length < 2 && !isLoading" class="py-16 flex flex-col items-center gap-3 text-muted-foreground">
      <i class="pi pi-search text-5xl opacity-20" />
      <p class="text-sm">Введіть мінімум 2 символи для пошуку</p>
    </div>

    <!-- ── Empty ── -->
    <div v-else-if="q.length >= 2 && !results.length && !isLoading" class="py-16 flex flex-col items-center gap-3">
      <i class="pi pi-inbox text-5xl text-muted-foreground/30" />
      <p class="text-sm text-muted-foreground">
        Нічого не знайдено для <b>"{{ q }}"</b>
      </p>
      <Button
        v-if="auth.user?.is_superadmin"
        text size="small"
        label="Спробувати перебудувати індекс"
        icon="pi pi-refresh"
        @click="reindex"
      />
    </div>

    <!-- ── Results ── -->
    <template v-else-if="results.length">

      <!-- DocType filter chips -->
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-sm text-muted-foreground mr-1">
          {{ results.length }} {{ results.length === 1 ? 'результат' : 'результатів' }}
        </span>

        <Chip
          label="Всі"
          :class="activeDoctype === null ? 'bg-primary text-white font-semibold' : 'cursor-pointer'"
          @click="activeDoctype = null"
        />
        <Chip
          v-for="chip in doctypeChips"
          :key="chip.doctype"
          :label="`${chip.doctype} (${chip.count})`"
          :class="activeDoctype === chip.doctype ? 'bg-primary text-white font-semibold' : 'cursor-pointer'"
          @click="activeDoctype = activeDoctype === chip.doctype ? null : chip.doctype"
        />
      </div>

      <!-- Results grouped by DocType -->
      <div v-for="group in groups" :key="group.doctype" class="flex flex-col gap-2">
        <div class="flex items-center gap-2 mt-2">
          <FileText class="size-4 text-muted-foreground" />
          <span class="text-xs font-bold uppercase tracking-wider text-muted-foreground">
            {{ group.doctype }}
          </span>
          <Tag :value="String(group.items.length)" severity="secondary" />
        </div>

        <DataTable
          :value="group.items"
          :row-hover="true"
          size="small"
          @row-click="(e: any) => navigateToDoc(e.data)"
          class="cursor-pointer rounded-lg overflow-hidden border border-border"
          :pt="{
            table: { class: 'w-full' },
            bodyRow: { class: 'hover:bg-muted/40 transition-colors cursor-pointer' },
          }"
        >
          <Column header="Назва" class="font-medium">
            <template #body="{ data }">
              <div class="flex items-center gap-2 py-0.5">
                <div class="size-7 rounded-md bg-primary/10 flex items-center justify-center shrink-0">
                  <FileText class="size-3.5 text-primary" />
                </div>
                <div>
                  <p class="text-sm font-semibold text-foreground">{{ data.display_title || data.name }}</p>
                  <p v-if="data.display_title && data.display_title !== data.name" class="text-xs text-muted-foreground">
                    {{ data.name }}
                  </p>
                </div>
              </div>
            </template>
          </Column>

          <Column header="Модуль" class="hidden sm:table-cell">
            <template #body="{ data }">
              <Tag v-if="data.module" :value="data.module" severity="secondary" />
            </template>
          </Column>
        </DataTable>
      </div>

    </template>
  </div>
</template>
