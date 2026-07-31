<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import draggable from 'vuedraggable'
import type { DocType, DocField } from '@/types'
import { docsApi } from '@/core/api/docs'

import { Plus, Calendar, FileText, Ellipsis } from '@lucide/vue'

const props = defineProps<{
  doctype: DocType
  columnField: string
  refreshKey?: number
}>()

const columnFieldDef = computed<DocField | undefined>(() =>
  props.doctype.fields.find(f => f.fieldname === props.columnField)
)

const columns = computed<string[]>(() => {
  if (!columnFieldDef.value?.options) return []
  return columnFieldDef.value.options.split('\n').map(s => s.trim()).filter(Boolean)
})

// Status colors and labels
const statusIndicatorMap = computed(() => {
  const sc = props.doctype.status_config
  if (!sc || sc.field !== props.columnField) return null
  const m = new Map<string, { color: string; label?: string | null }>()
  for (const ind of sc.indicators) m.set(ind.value, ind)
  return m
})

const colorToClass: Record<string, { border: string; bg: string; dot: string; text: string }> = {
  default: { border: 'border-slate-200', bg: 'bg-slate-50/50', dot: 'bg-slate-400', text: 'text-slate-700' },
  secondary: { border: 'border-slate-200', bg: 'bg-slate-50/50', dot: 'bg-slate-500', text: 'text-slate-700' },
  success: { border: 'border-green-200', bg: 'bg-green-50/50', dot: 'bg-green-500', text: 'text-green-700' },
  info: { border: 'border-blue-200', bg: 'bg-blue-50/50', dot: 'bg-blue-400', text: 'text-blue-700' },
  warn: { border: 'border-amber-200', bg: 'bg-amber-50/50', dot: 'bg-amber-400', text: 'text-amber-700' },
  danger: { border: 'border-red-200', bg: 'bg-red-50/50', dot: 'bg-red-500', text: 'text-red-700' },
  contrast: { border: 'border-zinc-300 dark:border-zinc-600', bg: 'bg-zinc-100/70 dark:bg-zinc-800/60', dot: 'bg-zinc-900 dark:bg-zinc-100', text: 'text-zinc-800 dark:text-zinc-100' },
  // Legacy colors for backward compatibility.
  gray: { border: 'border-slate-200', bg: 'bg-slate-50/50', dot: 'bg-slate-400', text: 'text-slate-700' },
  blue: { border: 'border-blue-200', bg: 'bg-blue-50/50', dot: 'bg-blue-400', text: 'text-blue-700' },
  green: { border: 'border-green-200', bg: 'bg-green-50/50', dot: 'bg-green-500', text: 'text-green-700' },
  yellow: { border: 'border-amber-200', bg: 'bg-amber-50/50', dot: 'bg-amber-400', text: 'text-amber-700' },
  orange: { border: 'border-amber-200', bg: 'bg-amber-50/50', dot: 'bg-amber-400', text: 'text-amber-700' },
  red: { border: 'border-red-200', bg: 'bg-red-50/50', dot: 'bg-red-500', text: 'text-red-700' },
  purple: { border: 'border-violet-200', bg: 'bg-violet-50/50', dot: 'bg-violet-400', text: 'text-violet-700' },
  pink: { border: 'border-pink-200', bg: 'bg-pink-50/50', dot: 'bg-pink-400', text: 'text-pink-700' },
}

function getColumnStyles(col: string) {
  const ind = statusIndicatorMap.value?.get(col)
  if (!ind) return colorToClass.secondary
  return colorToClass[ind.color] || colorToClass.secondary
}

function columnLabel(col: string) {
  return statusIndicatorMap.value?.get(col)?.label || col
}

const cardsByColumn = ref<Record<string, any[]>>({})
const isLoading = ref(true)
const quickAddInputs = ref<Record<string, string>>({})
const addingToColumn = ref<string | null>(null)

async function loadCards() {
  if (!props.doctype?.name) return
  isLoading.value = true
  try {
    const resp = await docsApi.list(props.doctype.name, {
      per_page: 500, // Fetch more for kanban
      sort: 'modified_at',
      order: 'desc'
    })
    const all = resp.data || []

    // Reset and group
    const newGroups: Record<string, any[]> = {}
    columns.value.forEach(col => newGroups[col] = [])

    all.forEach(doc => {
      const val = String(doc[props.columnField] || '')
      if (newGroups[val]) newGroups[val].push(doc)
    })

    cardsByColumn.value = newGroups
  } finally {
    isLoading.value = false
  }
}

async function onMove(col: string, evt: any) {
  if (!evt.added || !props.doctype?.name) return
  const card = evt.added.element
  try {
    await docsApi.update(props.doctype.name, String(card.id), { [props.columnField]: col })
  } catch (e) {
    console.error('Failed to update status', e)
    // Optionally revert local move if failed
    loadCards()
  }
}

async function quickAdd(col: string) {
  const val = quickAddInputs.value[col]?.trim()
  if (!val || !props.doctype?.name) return

  addingToColumn.value = col
  try {
    const titleField = props.doctype.title_field || 'name'
    const data = {
      [titleField]: val,
      [props.columnField]: col
    }
    const created = await docsApi.create(props.doctype.name, data)
    cardsByColumn.value[col].unshift(created)
    quickAddInputs.value[col] = ''
  } finally {
    addingToColumn.value = null
  }
}

function formatDate(val: any) {
  if (!val) return ''
  return new Date(val).toLocaleDateString('uk-UA', { day: 'numeric', month: 'short' })
}

onMounted(loadCards)
watch(() => props.doctype.name, loadCards)
watch(() => props.columnField, loadCards)
// Bumped by the shared header's Refresh button (kanban cards aren't on the shared query cache).
watch(() => props.refreshKey, (_v, old) => { if (old !== undefined) loadCards() })
</script>

<template>
  <div class="flex h-full gap-6 overflow-x-auto pb-6 px-4 custom-scrollbar bg-card pt-4">
    <!-- Columns -->
    <template v-if="!isLoading">
      <div v-for="col in columns" :key="col" class="flex-shrink-0 w-[320px] flex flex-col group/column h-full">
        <!-- Column Header -->
        <div class="flex items-center justify-between px-3 mb-4 shrink-0">
          <div class="flex items-center gap-3 overflow-hidden">
            <div class="size-2.5 rounded-full shrink-0 shadow-sm border border-white/20"
              :class="getColumnStyles(col).dot" />
            <h3 class="font-semibold text-xs text-foreground/70 truncate uppercase tracking-[0.15em]">
              {{ columnLabel(col) }}
            </h3>
            <Badge variant="secondary"
              class="!bg-muted/40 !text-muted-foreground !text-xs !font-semibold !px-2 !h-5 !min-w-6">{{ cardsByColumn[col]?.length || 0 }}</Badge>
          </div>
          <Button variant="ghost" size="sm" class="!size-7 !text-muted-foreground/40 hover:!text-foreground rounded-full"><Ellipsis class="size-4" /></Button>
        </div>

        <!-- Column Body -->
        <div
          class="flex-1 rounded-lg border bg-muted/10 border-border/40 group-hover/column:border-primary/20 group-hover/column:bg-muted/20 transition-all flex flex-col min-h-0 overflow-hidden">
          <!-- Quick Add -->
          <div class="p-3 border-b border-border/10">
            <div class="relative group/input">
              <Plus
                class="absolute left-3.5 top-1/2 -translate-y-1/2 size-4 text-muted-foreground/30 group-hover/input:text-primary transition-colors z-10" />
              <Input v-model="quickAddInputs[col]" placeholder="Швидке додавання..."
                class="!w-full !pl-10 !h-10 !text-xs !bg-background/40 hover:!bg-background !border-none !shadow-none focus:!ring-1 focus:!ring-primary/20 transition-all"
                @keyup.enter="quickAdd(col)" />
            </div>
          </div>

          <!-- Draggable Cards -->
          <draggable v-model="cardsByColumn[col]" group="kanban" item-key="id"
            class="flex-1 overflow-y-auto px-3 py-4 space-y-4 custom-scrollbar" ghost-class="ghost-class"
            drag-class="rotate-2" @change="onMove(col, $event)">
            <template #item="{ element: card }">
              <div
                class="bg-card hover:bg-card/80 border border-border/50 hover:border-primary/30 transition-colors duration-300 rounded-lg p-5 cursor-grab active:cursor-grabbing group shadow-sm relative overflow-hidden"
                @click="$router.push(`/grunt/${doctype.name}/${card.id || card.name}`)">

                <!-- Card Title -->
                <div class="flex items-start justify-between gap-3 relative z-10">
                  <p class="text-sm font-semibold text-foreground leading-snug line-clamp-2">
                    {{ card[doctype.title_field || 'name'] || card.id }}
                  </p>
                  <FileText
                    class="size-4 text-muted-foreground/10 group-hover:text-primary/20 transition-all shrink-0" />
                </div>

                <!-- Metadata -->
                <div class="flex items-center justify-between mt-6 relative z-10">
                  <div class="flex items-center gap-2">
                    <div v-if="card.owner" class="flex items-center gap-2 group-hover:bg-primary/5 px-2 py-1 rounded-full transition-colors" title="Власник">
                      <Avatar class="!size-5 !border !border-primary/20">
                        <AvatarFallback class="!text-xs !bg-primary/10 !text-primary">{{ card.owner.charAt(0).toUpperCase() }}</AvatarFallback>
                      </Avatar>
                      <span class="text-xs text-muted-foreground font-semibold truncate max-w-[80px]">
                        {{ card.owner.split('@')[0] }}
                      </span>
                    </div>
                  </div>
                  <div
                    class="flex items-center gap-2 text-xs text-muted-foreground/50 font-semibold uppercase tracking-wider bg-muted/30 px-2.5 py-1 rounded-lg border border-border/10">
                    <Calendar class="size-3" />
                    {{ formatDate(card.modified_at) }}
                  </div>
                </div>

                <!-- Interactive Indicator -->
                <div class="absolute left-0 top-0 bottom-0 w-1 bg-primary/0 group-hover:bg-primary/40 transition-all rounded-r-full" />
              </div>
            </template>
          </draggable>
        </div>
      </div>
    </template>

    <!-- Skeleton Loading -->
    <template v-else>
      <div v-for="i in 3" :key="i" class="flex-shrink-0 w-[320px] flex flex-col space-y-6 pt-10 px-2">
        <Skeleton class="h-6 w-32 ml-4 rounded-full" />
        <div class="flex-1 bg-muted/40 rounded-lg p-4 space-y-4 border border-border/20">
          <Skeleton class="h-10 w-full rounded-lg" />
          <Skeleton v-for="j in 3" :key="j" class="h-40 w-full rounded-lg" />
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  height: 8px;
  /* Slightly thicker horizontal scroll */
  width: 6px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: var(--muted);
  border-radius: 10px;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: var(--border);
  /* More visible by default */
  border-radius: 10px;
  border: 2px solid transparent;
  /* Padding effect */
  background-clip: content-box;
}

.custom-scrollbar:hover::-webkit-scrollbar-thumb {
  background: color-mix(in srgb, var(--primary) 30%, transparent);
  /* Change to primary color on hover */
  background-clip: content-box;
}

.ghost-class {
  border: 2px dashed var(--primary);
  background: color-mix(in srgb, var(--primary) 5%, transparent);
  opacity: 0.5 !important;
}
</style>
