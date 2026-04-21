<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import draggable from 'vuedraggable'
import type { DocType, DocField } from '@/types'
import { docsApi } from '@/core/api/docs'

import { Plus, Calendar, FileText } from '@lucide/vue'

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
</script>

<template>
  <div class="flex h-full gap-6 overflow-x-auto pb-6 px-4 custom-scrollbar bg-card/10 backdrop-blur-sm pt-4">
    <!-- Columns -->
    <template v-if="!isLoading">
      <div v-for="col in columns" :key="col" class="flex-shrink-0 w-[320px] flex flex-col group/column h-full">
        <!-- Column Header -->
        <div class="flex items-center justify-between px-3 mb-4 shrink-0">
          <div class="flex items-center gap-3 overflow-hidden">
            <div class="size-2.5 rounded-full shrink-0 shadow-sm border border-white/20"
              :class="getColumnStyles(col).dot" />
            <h3 class="font-black text-[11px] text-foreground/70 truncate uppercase tracking-[0.15em]">
              {{ columnLabel(col) }}
            </h3>
            <Badge :value="cardsByColumn[col]?.length || 0" severity="secondary"
              class="!bg-muted/40 !text-muted-foreground !text-[10px] !font-black !px-2 !h-5 !min-w-6" />
          </div>
          <Button icon="pi pi-ellipsis-h" text rounded size="small" class="!size-7 !text-muted-foreground/40 hover:!text-foreground" />
        </div>

        <!-- Column Body -->
        <div
          class="flex-1 rounded-[2rem] border bg-muted/10 border-border/40 group-hover/column:border-primary/20 group-hover/column:bg-muted/20 transition-all flex flex-col min-h-0 overflow-hidden shadow-inner-sm">
          <!-- Quick Add -->
          <div class="p-3 border-b border-border/10">
            <div class="relative group/input">
              <Plus
                class="absolute left-3.5 top-1/2 -translate-y-1/2 size-4 text-muted-foreground/30 group-hover/input:text-primary transition-colors z-10" />
              <InputText v-model="quickAddInputs[col]" placeholder="Швидке додавання..."
                class="!w-full !pl-10 !h-10 !text-xs !bg-background/40 hover:!bg-background !border-none !shadow-none focus:!ring-1 focus:!ring-primary/20 !rounded-2xl transition-all"
                @keyup.enter="quickAdd(col)" />
            </div>
          </div>

          <!-- Draggable Cards -->
          <draggable v-model="cardsByColumn[col]" group="kanban" item-key="id"
            class="flex-1 overflow-y-auto px-3 py-4 space-y-4 custom-scrollbar" ghost-class="ghost-class"
            drag-class="rotate-2" @change="onMove(col, $event)">
            <template #item="{ element: card }">
              <div
                class="bg-card hover:bg-card/80 border border-border/50 hover:border-primary/30 hover:shadow-xl hover:-translate-y-1 transition-all duration-300 rounded-[1.25rem] p-5 cursor-grab active:cursor-grabbing group shadow-sm relative overflow-hidden"
                @click="$router.push(`/grunt/${doctype.name}/${card.id || card.name}`)">
                
                <!-- Card Glow Backdrop -->
                <div class="absolute -right-4 -top-4 size-16 bg-primary/5 rounded-full blur-2xl group-hover:bg-primary/10 transition-colors" />

                <!-- Card Title -->
                <div class="flex items-start justify-between gap-3 relative z-10">
                  <p class="text-sm font-bold text-foreground leading-snug line-clamp-2">
                    {{ card[doctype.title_field || 'name'] || card.id }}
                  </p>
                  <FileText
                    class="size-4 text-muted-foreground/10 group-hover:text-primary/20 transition-all shrink-0" />
                </div>

                <!-- Metadata -->
                <div class="flex items-center justify-between mt-6 relative z-10">
                  <div class="flex items-center gap-2">
                    <div v-if="card.owner" class="flex items-center gap-2 group-hover:bg-primary/5 px-2 py-1 rounded-full transition-colors" title="Власник">
                      <Avatar :label="card.owner.charAt(0).toUpperCase()" shape="circle" size="normal"
                        class="!size-5 !text-[8px] !bg-primary/10 !text-primary !border !border-primary/20" />
                      <span class="text-[10px] text-muted-foreground font-semibold truncate max-w-[80px]">
                        {{ card.owner.split('@')[0] }}
                      </span>
                    </div>
                  </div>
                  <div
                    class="flex items-center gap-2 text-[10px] text-muted-foreground/50 font-black uppercase tracking-wider bg-muted/30 px-2.5 py-1 rounded-lg border border-border/10">
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
        <div class="flex-1 bg-muted/40 rounded-[2rem] p-4 space-y-4 border border-border/20">
          <Skeleton class="h-10 w-full rounded-2xl" />
          <Skeleton v-for="j in 3" :key="j" class="h-40 w-full rounded-[1.25rem]" />
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
