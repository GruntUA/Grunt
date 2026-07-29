<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { workspaceApi, type MyWork } from '@/core/api/workspace'
import { CheckSquare, AlertTriangle, Bell, ArrowRight, Inbox } from '@lucide/vue'

const router = useRouter()
const appStore = useAppStore()

const data = ref<MyWork | null>(null)
const loading = ref(true)

// Resolve which workspace exposes a given doctype, so task links navigate
// to the correct app route. Falls back to the first workspace.
function workspaceForDoctype(doctype: string): string {
  for (const ws of appStore.workspaces) {
    if (ws.items?.some(i => i.type === 'DocType' && i.link_to === doctype)) return ws.name
  }
  return appStore.workspaces[0]?.name ?? ''
}

const hasWork = computed(() => {
  const c = data.value?.counts
  return !!c && (c.assigned > 0 || c.unread > 0)
})

const tiles = computed(() => {
  const c = data.value?.counts ?? { assigned: 0, overdue: 0, unread: 0 }
  return [
    { key: 'assigned', label: 'Призначені мені', value: c.assigned, icon: CheckSquare, color: '#6366f1' },
    { key: 'overdue', label: 'Прострочені', value: c.overdue, icon: AlertTriangle, color: '#ef4444' },
    { key: 'unread', label: 'Непрочитані', value: c.unread, icon: Bell, color: '#3b82f6' },
  ]
})

function openTask(t: MyWork['assigned'][number]) {
  if (!t.reference_doctype || !t.reference_id) return
  const ws = workspaceForDoctype(t.reference_doctype)
  router.push(`/${ws}/${t.reference_doctype}/${t.reference_id}`)
}

function openNotification(n: MyWork['notifications'][number]) {
  if (n.doctype && n.doc_id) {
    router.push(`/${workspaceForDoctype(n.doctype)}/${n.doctype}/${n.doc_id}`)
  }
}

function formatDue(due: string | null): string {
  if (!due) return ''
  const d = new Date(due)
  if (isNaN(d.getTime())) return String(due)
  return d.toLocaleDateString('uk-UA', { day: '2-digit', month: '2-digit' })
}

onMounted(async () => {
  try {
    data.value = await workspaceApi.getMyWork()
  } catch {
    data.value = null
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section v-if="!loading && hasWork">
    <!-- Stat tiles -->
    <div class="grid grid-cols-3 gap-3 mb-4">
      <div v-for="tile in tiles" :key="tile.key"
        class="flex items-center gap-3 px-4 py-3 rounded-lg bg-card/60 border border-border/40">
        <div class="size-9 rounded-lg flex items-center justify-center shrink-0"
          :style="{ backgroundColor: tile.color + '18', color: tile.color }">
          <component :is="tile.icon" class="size-4" />
        </div>
        <div class="min-w-0">
          <p class="text-lg font-semibold text-foreground tabular-nums leading-none">{{ tile.value }}</p>
          <p class="text-xs text-muted-foreground/60 font-medium truncate">{{ tile.label }}</p>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <!-- Assigned tasks -->
      <div v-if="data && data.assigned.length"
        class="rounded-lg border border-border/40 bg-card/60 overflow-hidden">
        <div class="px-4 py-2.5 border-b border-border/20 flex items-center gap-2">
          <CheckSquare class="size-3.5 text-indigo-500/70" />
          <span class="text-xs font-semibold uppercase tracking-widest text-foreground/70">Мої задачі</span>
        </div>
        <button v-for="t in data.assigned.slice(0, 6)" :key="t.id"
          class="group w-full flex items-center gap-3 px-4 py-2.5 border-b border-border/10 last:border-0 hover:bg-primary/[0.03] transition-colors text-left"
          @click="openTask(t)">
          <div class="flex-1 min-w-0">
            <p class="text-sm font-semibold text-foreground truncate group-hover:text-primary transition-colors">
              {{ t.title }}
            </p>
            <span class="text-xs text-muted-foreground/50 font-mono">{{ t.reference_doctype }}</span>
          </div>
          <span v-if="t.overdue"
            class="text-xs font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-md bg-red-500/10 text-red-600 shrink-0">
            прострочено
          </span>
          <span v-else-if="t.due_date"
            class="text-xs text-muted-foreground/50 font-mono tabular-nums shrink-0">{{ formatDue(t.due_date) }}</span>
          <ArrowRight
            class="size-3.5 text-muted-foreground/20 group-hover:text-primary/50 transition-colors shrink-0" />
        </button>
      </div>

      <!-- Unread notifications -->
      <div v-if="data && data.notifications.length"
        class="rounded-lg border border-border/40 bg-card/60 overflow-hidden">
        <div class="px-4 py-2.5 border-b border-border/20 flex items-center gap-2">
          <Bell class="size-3.5 text-blue-500/70" />
          <span class="text-xs font-semibold uppercase tracking-widest text-foreground/70">Сповіщення</span>
        </div>
        <button v-for="n in data.notifications.slice(0, 6)" :key="n.name"
          class="group w-full flex items-center gap-3 px-4 py-2.5 border-b border-border/10 last:border-0 hover:bg-primary/[0.03] transition-colors text-left"
          :class="{ 'cursor-default': !n.doctype }"
          @click="openNotification(n)">
          <div class="size-1.5 rounded-full bg-blue-500 shrink-0" />
          <p class="flex-1 min-w-0 text-sm text-foreground truncate group-hover:text-primary transition-colors">
            {{ n.subject }}
          </p>
          <ArrowRight v-if="n.doctype"
            class="size-3.5 text-muted-foreground/20 group-hover:text-primary/50 transition-colors shrink-0" />
        </button>
      </div>

      <!-- Empty column filler when only one list has content -->
      <div v-if="data && (data.assigned.length === 0) !== (data.notifications.length === 0)"
        class="hidden lg:flex flex-col items-center justify-center rounded-lg border border-dashed border-border/30 text-center p-6">
        <Inbox class="size-6 text-muted-foreground/30 mb-2" />
        <p class="text-xs text-muted-foreground/50">
          {{ data.assigned.length === 0 ? 'Немає призначених задач' : 'Немає нових сповіщень' }}
        </p>
      </div>
    </div>
  </section>
</template>
