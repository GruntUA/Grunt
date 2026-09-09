<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { formatDayMonth } from '@/core/datetime'
import { VueDraggable } from 'vue-draggable-plus'
import type { DocType, DocField } from '@/types'
import { docsApi } from '@/core/api/docs'
import { parseSelectValues } from '@/lib/selectOptions'

import { Plus, Calendar, Ellipsis } from '@lucide/vue'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
const props = defineProps<{
  doctype: DocType
  columnField: string
  refreshKey?: number
}>()

const columnFieldDef = computed<DocField | undefined>(() =>
  props.doctype.fields.find(f => f.fieldname === props.columnField)
)

const columns = computed<string[]>(() => parseSelectValues(columnFieldDef.value?.options))

// Status colors and labels
const statusIndicatorMap = computed(() => {
  if (props.doctype.status_field !== props.columnField) return null
  const m = new Map<string, { color: string; label?: string | null }>()
  for (const ind of props.doctype.status_indicators ?? []) m.set(ind.value, ind)
  return m
})

const dotClass: Record<string, string> = {
  default: 'bg-slate-400',
  secondary: 'bg-slate-400',
  success: 'bg-green-500',
  info: 'bg-blue-400',
  warn: 'bg-amber-400',
  danger: 'bg-red-500',
  contrast: 'bg-zinc-900 dark:bg-zinc-100',
  // Legacy colors for backward compatibility.
  gray: 'bg-slate-400',
  blue: 'bg-blue-400',
  green: 'bg-green-500',
  yellow: 'bg-amber-400',
  orange: 'bg-amber-400',
  red: 'bg-red-500',
  purple: 'bg-violet-400',
  pink: 'bg-pink-400',
}

function columnDot(col: string) {
  const ind = statusIndicatorMap.value?.get(col)
  return dotClass[ind?.color ?? ''] || dotClass.secondary
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
  const card = evt?.data
  if (!card || !props.doctype?.name) return
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
  return formatDayMonth(val as string)
}

onMounted(loadCards)
watch(() => props.doctype.name, loadCards)
watch(() => props.columnField, loadCards)
// Bumped by the shared header's Refresh button (kanban cards aren't on the shared query cache).
watch(() => props.refreshKey, (_v, old) => { if (old !== undefined) loadCards() })
</script>

<template>
  <div class="custom-scrollbar flex h-full gap-3 overflow-x-auto bg-card p-4">
    <!-- Columns -->
    <template v-if="!isLoading">
      <div v-for="col in columns" :key="col" class="flex h-full w-80 shrink-0 flex-col">
        <!-- Column Header -->
        <div class="mb-2 flex items-center justify-between px-1">
          <div class="flex items-center gap-2 overflow-hidden">
            <span class="size-2 shrink-0 rounded-full" :class="columnDot(col)" />
            <h3 class="truncate text-sm font-medium">{{ columnLabel(col) }}</h3>
            <span class="text-muted-foreground">{{ cardsByColumn[col]?.length || 0 }}</span>
          </div>
          <Button variant="ghost" size="icon" class="size-6 text-muted-foreground">
            <Ellipsis class="size-4" />
          </Button>
        </div>

        <!-- Column Body -->
        <div class="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border bg-muted/30">
          <!-- Quick Add -->
          <div class="p-2">
            <div class="relative">
              <Plus class="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input v-model="quickAddInputs[col]" placeholder="Швидке додавання..." class="h-8 pl-8"
                @keyup.enter="quickAdd(col)" />
            </div>
          </div>

          <!-- Draggable Cards -->
          <VueDraggable v-model="cardsByColumn[col]" group="kanban"
            class="custom-scrollbar flex-1 space-y-2 overflow-y-auto px-2 pb-2" ghost-class="ghost-class"
            drag-class="rotate-1" @add="onMove(col, $event)">
            <div
              v-for="card in cardsByColumn[col]"
              :key="card.id"
              class="cursor-grab rounded-lg border bg-card p-3 shadow-sm transition-colors hover:border-primary/40 active:cursor-grabbing"
              @click="$router.push(`/grunt/${doctype.name}/${card.id || card.name}`)">

              <p class="line-clamp-2 text-sm font-medium leading-tight">
                {{ card[doctype.title_field || 'name'] || card.id }}
              </p>

              <div class="mt-3 flex items-center justify-between gap-2 text-muted-foreground">
                <div v-if="card.owner" class="flex items-center gap-1.5 overflow-hidden" title="Власник">
                  <Avatar class="size-5 shrink-0">
                    <AvatarFallback class="text-xs">{{ card.owner.charAt(0).toUpperCase() }}</AvatarFallback>
                  </Avatar>
                  <span class="truncate">{{ card.owner.split('@')[0] }}</span>
                </div>
                <div class="flex shrink-0 items-center gap-1">
                  <Calendar class="size-3" />
                  {{ formatDate(card.modified_at) }}
                </div>
              </div>
            </div>
          </VueDraggable>
        </div>
      </div>
    </template>

    <!-- Skeleton Loading -->
    <template v-else>
      <div v-for="i in 3" :key="i" class="flex w-80 shrink-0 flex-col">
        <div class="mb-2 flex items-center gap-2 px-1">
          <Skeleton class="size-2 rounded-full" />
          <Skeleton class="h-4 w-24 rounded" />
        </div>
        <div class="flex-1 space-y-2 rounded-lg border bg-muted/30 p-2">
          <Skeleton class="h-8 w-full rounded-md" />
          <Skeleton v-for="j in 3" :key="j" class="h-20 w-full rounded-lg" />
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* Visible-but-neutral scrollbar for the horizontal column strip (matches GanttView). */
.custom-scrollbar::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 10px;
  border: 2px solid transparent;
  background-clip: padding-box;
}

.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background-color: var(--muted-foreground);
}

.ghost-class {
  border: 1px dashed var(--primary);
  background: color-mix(in srgb, var(--primary) 5%, transparent);
  opacity: 0.5 !important;
}
</style>
