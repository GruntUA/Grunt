<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useWorkspaceStore } from '@/stores/workspace'
import { workspaceApi } from '@/core/api/workspace'
import type { SearchResult } from '@/core/api/workspace'

const router = useRouter()
const wsStore = useWorkspaceStore()

const query = ref('')
const isOpen = ref(false)
const results = ref<SearchResult[]>([])
const searching = ref(false)

let debounceTimer: ReturnType<typeof setTimeout>

watch(query, (v) => {
  clearTimeout(debounceTimer)
  if (!v.trim()) {
    results.value = []
    return
  }
  debounceTimer = setTimeout(async () => {
    searching.value = true
    try {
      results.value = await workspaceApi.search(v.trim())
    } catch {
      results.value = []
    } finally {
      searching.value = false
    }
  }, 300)
})

const filteredWorkspaces = computed(() => {
  if (!query.value.trim()) return []
  const q = query.value.toLowerCase()
  return wsStore.workspaces.filter(w =>
    w.label.toLowerCase().includes(q) || w.name.toLowerCase().includes(q)
  )
})

function onFocus() {
  isOpen.value = true
}

function close() {
  isOpen.value = false
  query.value = ''
  results.value = []
}

function goToWorkspace(name: string) {
  close()
  router.push(`/${name}`)
}

function goToDoc(r: SearchResult) {
  close()
  // Find workspace that has this doctype
  const ws = wsStore.workspaces.find(w =>
    w.items.some(item => item.link_to === r.doctype)
  )
  const prefix = ws ? `/${ws.name}` : ''
  router.push(`${prefix}/list/${r.doctype}/${r.id}`)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') close()
}
</script>

<template>
  <div class="relative w-full max-w-xl mx-auto">
    <div class="relative">
      <span class="absolute left-3 top-1/2 -translate-y-1/2 text-[--grunt-text-muted]">🔍</span>
      <input
        v-model="query"
        type="text"
        placeholder="Пошук по додатках та документах..."
        class="w-full pl-10 pr-4 py-2.5 text-sm bg-[--grunt-surface] border border-[--grunt-border] rounded-[--grunt-radius-lg] focus:outline-none focus:border-[--grunt-primary] focus:ring-1 focus:ring-[--grunt-primary] transition-colors"
        @focus="onFocus"
        @keydown="onKeydown"
      />
    </div>

    <!-- Results overlay -->
    <div
      v-if="isOpen && query.trim()"
      class="absolute top-full mt-2 w-full bg-[--grunt-surface] border border-[--grunt-border] rounded-[--grunt-radius-lg] shadow-[--grunt-shadow-md] z-50 max-h-80 overflow-y-auto"
    >
      <!-- Workspace matches -->
      <div v-if="filteredWorkspaces.length > 0">
        <p class="px-4 py-2 text-xs font-semibold text-[--grunt-text-muted] uppercase tracking-wider">Додатки</p>
        <button
          v-for="ws in filteredWorkspaces"
          :key="ws.name"
          class="w-full flex items-center gap-3 px-4 py-2 text-sm hover:bg-[--grunt-surface-secondary] transition-colors"
          @click="goToWorkspace(ws.name)"
        >
          <span>{{ ws.icon }}</span>
          <span class="text-[--grunt-text-primary]">{{ ws.label }}</span>
        </button>
      </div>

      <!-- Document results -->
      <div v-if="results.length > 0">
        <p class="px-4 py-2 text-xs font-semibold text-[--grunt-text-muted] uppercase tracking-wider border-t border-[--grunt-border]">Документи</p>
        <button
          v-for="r in results"
          :key="r.id"
          class="w-full flex items-center gap-3 px-4 py-2 text-sm hover:bg-[--grunt-surface-secondary] transition-colors"
          @click="goToDoc(r)"
        >
          <span class="text-xs px-1.5 py-0.5 rounded bg-[--grunt-surface-secondary] text-[--grunt-text-muted]">{{ r.doctype }}</span>
          <span class="text-[--grunt-text-primary]">{{ r.display_title }}</span>
        </button>
      </div>

      <!-- Loading -->
      <div v-if="searching" class="px-4 py-3 text-sm text-[--grunt-text-muted] text-center">
        Шукаю...
      </div>

      <!-- No results -->
      <div v-if="!searching && query.trim() && !filteredWorkspaces.length && !results.length" class="px-4 py-3 text-sm text-[--grunt-text-muted] text-center">
        Нічого не знайдено
      </div>
    </div>
  </div>

  <!-- Backdrop -->
  <div v-if="isOpen && query.trim()" class="fixed inset-0 z-40" @click="close" />
</template>
