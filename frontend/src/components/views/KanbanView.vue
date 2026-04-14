<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import draggable from 'vuedraggable'
import type { DocType, DocField } from '@/types'
import { docsApi } from '@/core/api/docs'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { Plus, MoreHorizontal, User, Calendar, FileText } from '@lucide/vue'
import { Input } from '@/components/ui/input'

const props = defineProps<{
  doctype: DocType
  columnField: string
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
  gray: { border: 'border-slate-200', bg: 'bg-slate-50/50', dot: 'bg-slate-400', text: 'text-slate-700' },
  blue: { border: 'border-blue-200', bg: 'bg-blue-50/50', dot: 'bg-blue-400', text: 'text-blue-700' },
  green: { border: 'border-green-200', bg: 'bg-green-50/50', dot: 'bg-green-500', text: 'text-green-700' },
  yellow: { border: 'border-yellow-200', bg: 'bg-yellow-50/50', dot: 'bg-yellow-400', text: 'text-yellow-700' },
  orange: { border: 'border-orange-200', bg: 'bg-orange-50/50', dot: 'bg-orange-400', text: 'text-orange-700' },
  red: { border: 'border-red-200', bg: 'bg-red-50/50', dot: 'bg-red-500', text: 'text-red-700' },
  purple: { border: 'border-purple-200', bg: 'bg-purple-50/50', dot: 'bg-purple-400', text: 'text-purple-700' },
  pink: { border: 'border-pink-200', bg: 'bg-pink-50/50', dot: 'bg-pink-400', text: 'text-pink-700' },
}

function getColumnStyles(col: string) {
  const ind = statusIndicatorMap.value?.get(col)
  if (!ind) return colorToClass.gray
  return colorToClass[ind.color] || colorToClass.gray
}

function columnLabel(col: string) {
  return statusIndicatorMap.value?.get(col)?.label || col
}

const cardsByColumn = ref<Record<string, any[]>>({})
const isLoading = ref(true)
const quickAddInputs = ref<Record<string, string>>({})
const addingToColumn = ref<string | null>(null)

async function loadCards() {
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
  if (!evt.added) return
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
  if (!val) return

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
</script>

<template>
  <div class="flex h-full gap-5 overflow-x-scroll pb-6 px-1 custom-scrollbar">
    <!-- Columns -->
    <template v-if="!isLoading">
      <div v-for="col in columns" :key="col" class="flex-shrink-0 w-[300px] flex flex-col group/column">
        <!-- Column Header -->
        <div class="flex items-center justify-between px-2 mb-3">
          <div class="flex items-center gap-2.5 overflow-hidden">
            <div class="size-2.5 rounded-full shrink-0 shadow-[0_0_8px_rgba(0,0,0,0.1)]"
              :class="getColumnStyles(col).dot" />
            <h3 class="font-bold text-sm text-foreground/90 truncate uppercase tracking-wider">
              {{ columnLabel(col) }}
            </h3>
            <Badge variant="secondary"
              class="h-5 px-1.5 text-[10px] bg-muted/40 text-muted-foreground font-bold tabular-nums">
              {{ cardsByColumn[col]?.length || 0 }}
            </Badge>
          </div>
          <button class="text-muted-foreground/30 hover:text-foreground transition-colors p-1">
            <MoreHorizontal class="size-4" />
          </button>
        </div>

        <!-- Column Body -->
        <div
          class="flex-1 rounded-2xl border bg-muted/20 border-transparent group-hover/column:border-primary/10 group-hover/column:bg-muted/30 transition-all flex flex-col min-h-0"
          :class="[getColumnStyles(col).bg]">
          <!-- Quick Add -->
          <div class="p-2 border-b border-transparent group-hover/column:border-border/30 transition-all">
            <div class="relative group/input">
              <Plus
                class="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground/40 group-hover/input:text-primary transition-colors" />
              <Input v-model="quickAddInputs[col]" placeholder="Швидке додавання..."
                class="h-9 pl-8 text-xs bg-background/40 hover:bg-background border-none shadow-none focus-visible:ring-1 focus-visible:ring-primary/20 transition-all"
                @keyup.enter="quickAdd(col)" />
            </div>
          </div>

          <!-- Draggable Cards -->
          <draggable v-model="cardsByColumn[col]" group="kanban" item-key="id"
            class="flex-1 overflow-y-auto px-2 py-3 space-y-3 custom-scrollbar" ghost-class="opacity-50"
            drag-class="rotate-1" @change="onMove(col, $event)">
            <template #item="{ element: card }">
              <div
                class="bg-card hover:bg-card/95 border hover:border-primary/30 hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200 rounded-xl p-4 cursor-grab active:cursor-grabbing group shadow-sm relative overflow-hidden"
                @click="$router.push(`/grunt/list/${doctype.name}/${card.id || card.name}`)">
                <!-- Card Title -->
                <div class="flex items-start justify-between gap-2">
                  <p class="text-sm font-semibold text-foreground/90 leading-tight line-clamp-2">
                    {{ card[doctype.title_field || 'name'] || card.id }}
                  </p>
                  <FileText
                    class="size-3.5 text-muted-foreground/20 group-hover:text-primary/30 transition-colors shrink-0" />
                </div>

                <!-- Metadata -->
                <div class="flex items-center justify-between mt-4">
                  <div class="flex items-center gap-3">
                    <div v-if="card.owner" class="flex items-center gap-1.5" title="Власник">
                      <div
                        class="size-5 rounded-full bg-primary/10 flex items-center justify-center border border-primary/20 shadow-inner">
                        <User class="size-2.5 text-primary" />
                      </div>
                      <span class="text-[10px] text-muted-foreground font-medium truncate max-w-[80px]">
                        {{ card.owner.split('@')[0] }}
                      </span>
                    </div>
                  </div>
                  <div
                    class="flex items-center gap-1.5 text-[10px] text-muted-foreground/60 font-medium whitespace-nowrap bg-muted/50 px-2 py-0.5 rounded-full">
                    <Calendar class="size-3" />
                    {{ formatDate(card.modified_at) }}
                  </div>
                </div>

                <!-- Decorative Grip Handle -->
                <div class="absolute left-0 top-0 bottom-0 w-1 bg-primary/0 group-hover:bg-primary/20 transition-all" />
              </div>
            </template>
          </draggable>
        </div>
      </div>
    </template>

    <!-- Skeleton Loading -->
    <template v-else>
      <div v-for="i in 3" :key="i" class="flex-shrink-0 w-[300px] flex flex-col space-y-4 pt-10">
        <Skeleton class="h-6 w-32 ml-4 rounded-full" />
        <div class="flex-1 bg-muted/40 rounded-2xl p-3 space-y-3 border border-border/20">
          <Skeleton class="h-10 w-full rounded-xl" />
          <Skeleton v-for="j in 4" :key="j" class="h-32 w-full rounded-xl" />
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
  background: rgba(0, 0, 0, 0.02);
  border-radius: 10px;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.15);
  /* More visible by default */
  border-radius: 10px;
  border: 2px solid transparent;
  /* Padding effect */
  background-clip: content-box;
}

.custom-scrollbar:hover::-webkit-scrollbar-thumb {
  background: rgba(var(--primary), 0.3);
  /* Change to primary color on hover */
  background-clip: content-box;
}

.ghost-class {
  border: 2px dashed rgb(var(--primary));
  background: rgba(var(--primary), 0.05);
  opacity: 0.5 !important;
}
</style>
