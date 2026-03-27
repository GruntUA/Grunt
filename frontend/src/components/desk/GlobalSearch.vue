<script setup lang="ts">
import { ref, watch, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useWorkspaceStore } from '@/stores/workspace'
import { workspaceApi } from '@/core/api/workspace'
import type { SearchResult } from '@/core/api/workspace'
import { Search, ArrowRight, FileText, AppWindow } from 'lucide-vue-next'

const router = useRouter()
const wsStore = useWorkspaceStore()

const query = ref('')
const isOpen = ref(false)
const results = ref<SearchResult[]>([])
const searching = ref(false)
const inputRef = ref<HTMLInputElement | null>(null)

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
  const ws = wsStore.workspaces.find(w =>
    w.items.some(item => item.link_to === r.doctype)
  )
  const wsName = ws?.name ?? 'grunt'
  if (r.doctype === 'DocType') {
    router.push(`/${wsName}/list/DocType/${r.id}`)
    return
  }
  router.push(`/${wsName}/list/${r.doctype}/${r.id}`)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') close()
}

function handleGlobalKeydown(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault()
    inputRef.value?.focus()
    isOpen.value = true
  }
}

onMounted(() => document.addEventListener('keydown', handleGlobalKeydown))
onUnmounted(() => document.removeEventListener('keydown', handleGlobalKeydown))
</script>

<template>
  <div class="relative w-full max-w-xl mx-auto">
    <div class="relative group">
      <Search class="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/70 group-focus-within:text-primary transition-colors" />
      <input
        ref="inputRef"
        v-model="query"
        type="text"
        placeholder="Пошук по додатках та документах..."
        class="w-full pl-10 pr-16 py-3 text-sm bg-card border border-border/60 rounded-xl shadow-sm focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/10 hover:border-border transition-all placeholder:text-muted-foreground/50"
        @focus="onFocus"
        @keydown="onKeydown"
      />
      <kbd class="absolute right-3 top-1/2 -translate-y-1/2 hidden sm:inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md bg-muted text-[10px] font-medium text-muted-foreground border border-border/60">
        <span class="text-xs">&#8984;</span>K
      </kbd>
    </div>

    <!-- Results overlay -->
    <Transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0 -translate-y-1"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition duration-100 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="isOpen && query.trim()"
        class="absolute top-full mt-2 w-full bg-card border border-border/60 rounded-xl shadow-xl shadow-black/[0.08] z-50 max-h-80 overflow-y-auto overflow-x-hidden"
      >
        <!-- Workspace matches -->
        <div v-if="filteredWorkspaces.length > 0" class="p-1.5">
          <p class="px-2.5 py-1.5 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Додатки</p>
          <button
            v-for="ws in filteredWorkspaces"
            :key="ws.name"
            class="w-full flex items-center gap-3 px-2.5 py-2 text-sm rounded-lg hover:bg-muted transition-colors group"
            @click="goToWorkspace(ws.name)"
          >
            <AppWindow class="w-4 h-4 text-muted-foreground/70" />
            <span class="text-foreground flex-1 text-left">{{ ws.label }}</span>
            <ArrowRight class="w-3.5 h-3.5 text-muted-foreground/50 opacity-0 group-hover:opacity-100 transition-opacity" />
          </button>
        </div>

        <!-- Document results -->
        <div v-if="results.length > 0" class="p-1.5" :class="{ 'border-t border-border': filteredWorkspaces.length > 0 }">
          <p class="px-2.5 py-1.5 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Документи</p>
          <button
            v-for="r in results"
            :key="r.id"
            class="w-full flex items-center gap-3 px-2.5 py-2 text-sm rounded-lg hover:bg-muted transition-colors group"
            @click="goToDoc(r)"
          >
            <FileText class="w-4 h-4 text-muted-foreground/70" />
            <span class="text-foreground flex-1 text-left">{{ r.display_title }}</span>
            <span class="text-[11px] px-1.5 py-0.5 rounded-md bg-muted text-muted-foreground font-medium">{{ r.doctype }}</span>
          </button>
        </div>

        <!-- Loading -->
        <div v-if="searching" class="px-4 py-6 text-sm text-muted-foreground text-center">
          <div class="inline-block w-4 h-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin mr-2 align-middle" />
          Шукаю...
        </div>

        <!-- No results -->
        <div v-if="!searching && query.trim() && !filteredWorkspaces.length && !results.length" class="px-4 py-6 text-sm text-muted-foreground/70 text-center">
          Нічого не знайдено за запитом "{{ query }}"
        </div>
      </div>
    </Transition>
  </div>

  <!-- Backdrop -->
  <div v-if="isOpen && query.trim()" class="fixed inset-0 z-40" @click="close" />
</template>
