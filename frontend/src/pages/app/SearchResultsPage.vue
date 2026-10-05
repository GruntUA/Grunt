<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { tn } from '@/plugins/i18n'
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/core/composables/useToast'
import client from '@/core/api/client'
import { FileText, Search, X, Inbox, RefreshCw } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

const { t } = useI18n()

const props = defineProps<{ workspaceName?: string }>()

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const auth = useAuthStore()
const toast = useToast()

// State

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

// Search

async function runSearch() {
  const query = q.value.trim()
  if (query.length < 2) { results.value = []; return }

  isLoading.value = true
  try {
    const res = await client.get('/api/v1/method/grunt.api.v1.search.global_search', { params: { q: query, limit: 50 } })
    results.value = (res.data?.data ?? []) as SearchResult[]
    activeDoctype.value = null
  } catch {
    toast.error(t('Search error'))
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
  if (appStore.workspaces.length === 0) await appStore.loadAll()
  if (q.value) runSearch()
})

// Grouping

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

// Navigation

function navigateToDoc(r: SearchResult) {
  const ws = appStore.workspaces.find(w => w.items?.some(i => i.link_to === r.doctype))
  const workspace = ws?.name ?? props.workspaceName ?? 'grunt'
  router.push(`/${workspace}/${r.doctype}/${r.id}`)
}

// Reindex

async function reindex() {
  isReindexing.value = true
  try {
    const res = await client.post('/api/v1/method/grunt.api.v1.search.rebuild_index')
    toast.success(t('Index rebuilt: {n} documents', { n: String(res.data?.data?.indexed || 0) }))
    await runSearch()
  } catch {
    toast.error(t('Index rebuild error'))
  } finally {
    isReindexing.value = false
  }
}
</script>

<template>
  <div class="flex flex-col gap-6 p-6 max-w-5xl mx-auto w-full">

    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-semibold text-foreground">{{ t('Global search') }}</h1>
        <p class="text-muted-foreground mt-0.5">{{ t('Search across all documents') }}</p>
      </div>
      <Button
        v-if="auth.isSystemManager"
        variant="outline"
        size="sm"
        :disabled="isReindexing"
        @click="reindex"
      ><RefreshCw class="size-4 mr-2" :class="{ 'animate-spin': isReindexing }" />{{ t('Rebuild index') }}</Button>
    </div>

    <!-- Search Input -->
    <div class="relative">
      <Search class="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
      <Input
        v-model="inputQ"
        :placeholder="t('Type at least 2 characters to search...')"
        class="w-full h-11 pl-9 pr-9"
        autofocus
      />
      <X v-if="inputQ" class="absolute right-3 top-1/2 -translate-y-1/2 size-4 cursor-pointer text-muted-foreground hover:text-foreground transition-colors" @click="inputQ = ''" />
    </div>

    <!-- Loading -->
    <div v-if="isLoading" class="flex flex-col gap-2">
      <div class="h-[3px] w-full overflow-hidden rounded-full bg-primary/20">
        <div class="h-full w-1/3 rounded-full bg-primary animate-progress-indeterminate" />
      </div>
      <p class="text-muted-foreground text-center">{{ t('Searching...') }}</p>
    </div>

    <!-- Too short -->
    <div v-else-if="q.length < 2 && !isLoading" class="py-16 flex flex-col items-center gap-3 text-muted-foreground">
      <Search class="text-5xl opacity-20" />
      <p>{{ t('Type at least 2 characters to search') }}</p>
    </div>

    <!-- Empty -->
    <div v-else-if="q.length >= 2 && !results.length && !isLoading" class="py-16 flex flex-col items-center gap-3">
      <Inbox class="text-5xl text-muted-foreground/30" />
      <p class="text-muted-foreground">
        {{ t('Nothing found for') }} <b>"{{ q }}"</b>
      </p>
      <Button variant="ghost" v-if="auth.isSystemManager" size="sm" @click="reindex"><RefreshCw class="size-4 mr-2" />{{ t('Try rebuilding the index') }}</Button>
    </div>

    <!-- Results -->
    <template v-else-if="results.length">

      <!-- DocType filter chips -->
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-muted-foreground mr-1">
          {{ tn('{n} result', '{n} results', results.length) }}
        </span>

        <Badge
          variant="outline"
          :class="activeDoctype === null ? 'bg-primary text-white font-semibold' : 'cursor-pointer'"
          @click="activeDoctype = null"
        >{{ t('All') }}</Badge>
        <Badge
          v-for="chip in doctypeChips"
          :key="chip.doctype"
          variant="outline"
          :class="activeDoctype === chip.doctype ? 'bg-primary text-white font-semibold' : 'cursor-pointer'"
          @click="activeDoctype = activeDoctype === chip.doctype ? null : chip.doctype"
        >{{ chip.doctype }} ({{ chip.count }})</Badge>
      </div>

      <!-- Results grouped by DocType -->
      <div v-for="group in groups" :key="group.doctype" class="flex flex-col gap-2">
        <div class="flex items-center gap-2 mt-2">
          <FileText class="size-4 text-muted-foreground" />
          <span class="font-semibold uppercase tracking-wider text-muted-foreground">
            {{ group.doctype }}
          </span>
          <Badge variant="secondary">{{ group.items.length }}</Badge>
        </div>

        <Table class="rounded-lg overflow-hidden border border-border">
          <TableHeader>
            <TableRow>
              <TableHead class="font-medium">{{ t('Name') }}</TableHead>
              <TableHead class="hidden sm:table-cell">{{ t('Module') }}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow
              v-for="item in group.items" :key="item.idx_id"
              class="cursor-pointer hover:bg-muted/40 transition-colors"
              @click="navigateToDoc(item)"
            >
              <TableCell>
                <div class="flex items-center gap-2 py-0.5">
                  <div class="size-7 rounded-md bg-primary/10 flex items-center justify-center shrink-0">
                    <FileText class="size-3.5 text-primary" />
                  </div>
                  <div>
                    <p class="font-semibold text-foreground">{{ item.display_title || item.name }}</p>
                    <p v-if="item.display_title && item.display_title !== item.name" class="text-xs text-muted-foreground">
                      {{ item.name }}
                    </p>
                  </div>
                </div>
              </TableCell>
              <TableCell class="hidden sm:table-cell">
                <Badge v-if="item.module" variant="secondary">{{ item.module }}</Badge>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </div>

    </template>
  </div>
</template>
