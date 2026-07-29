<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import type { DocField } from '@/types'
import type { ListColumn } from '@/core/composables/useListColumns'

import { FileX, Check, ImageIcon } from '@lucide/vue'

const props = defineProps<{
  rows: Record<string, unknown>[]
  columns: ListColumn[]
  fields: DocField[]
  doctype: string
  imageField?: string
  workspace?: string
  isLoading?: boolean
  selection?: {
    selectedIds: string[]
    allSelected: boolean
    isSelected: (id: string) => boolean
    toggle: (id: string) => void
  }
}>()

const router = useRouter()

const fieldMap = computed(() => {
  const m: Record<string, DocField> = {}
  for (const f of props.fields) m[f.fieldname] = f
  return m
})

// Image field to use as card thumbnail
const imageField = computed<string | null>(() => {
  if (props.imageField) return props.imageField
  const f = props.fields.find(f => f.fieldtype === 'Image' || f.fieldtype === 'Attach')
  return f?.fieldname ?? null
})

// Primary title column (first visible column)
const titleCol = computed(() => props.columns[0] ?? null)

// Rest of visible columns (for card body), skip image field
const bodyColumns = computed(() =>
  props.columns.slice(1).filter(c => c.key !== imageField.value).slice(0, 4)
)

const hasSelection = computed(() => !!props.selection?.selectedIds?.length || !!props.selection?.allSelected)

function onCardClick(e: MouseEvent, row: Record<string, unknown>) {
  if (props.selection && (hasSelection.value || e.ctrlKey || e.metaKey)) {
    props.selection.toggle(String(row.id))
    return
  }
  navigateToDoc(row)
}

function onCheckboxClick(e: MouseEvent, row: Record<string, unknown>) {
  e.stopPropagation()
  props.selection?.toggle(String(row.id))
}

function navigateToDoc(row: Record<string, unknown>) {
  const ws = props.workspace ?? 'grunt'
  router.push(`/${ws}/${props.doctype}/${row.id}`)
}

function formatCell(val: unknown): string {
  if (val === null || val === undefined || val === '') return '—'
  return String(val)
}

function getFieldType(key: string): string {
  return fieldMap.value[key]?.fieldtype ?? 'Text'
}

function formatDate(val: unknown, type: string): string {
  if (!val) return '—'
  try {
    const d = new Date(String(val))
    if (isNaN(d.getTime())) return String(val)
    if (type === 'Date') return d.toLocaleDateString('uk-UA')
    return d.toLocaleString('uk-UA', { dateStyle: 'short', timeStyle: 'short' })
  } catch {
    return String(val)
  }
}
</script>

<template>
  <div class="gallery-view-container min-h-64 px-1">
    <!-- Empty state -->
    <div v-if="!isLoading && !rows.length" class="flex flex-col items-center justify-center py-32 text-center bg-card rounded-lg border border-dashed border-border/40 space-y-6">
      <div class="size-20 rounded-lg bg-primary/5 flex items-center justify-center">
          <FileX class="size-10 text-primary/40" />
      </div>
      <div class="space-y-2">
        <h3 class="text-xl font-semibold text-foreground">Записів не знайдено</h3>
        <p class="text-sm text-muted-foreground max-w-xs mx-auto font-medium">Спробуйте змінити фільтри або додати новий документ у цю категорію</p>
      </div>
    </div>

    <!-- Skeleton -->
    <div v-else-if="isLoading && !rows.length"
      class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-8">
      <div v-for="i in 8" :key="i" class="rounded-lg border border-border/20 bg-card/50 p-0 overflow-hidden shadow-sm">
        <Skeleton class="h-[12rem] !rounded-none" />
        <div class="p-6 space-y-4">
            <Skeleton class="w-[85%] h-[1.5rem] rounded-lg" />
            <Skeleton class="w-[45%] h-[0.8rem] rounded-md" />
            <div class="pt-4 border-t border-border/10 space-y-3">
              <Skeleton v-for="j in 2" :key="j" class="w-full h-[0.6rem] rounded-full" />
            </div>
        </div>
      </div>
    </div>

    <!-- Gallery grid -->
    <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-8">
      <div
        v-for="row in rows"
        :key="String(row.id)"
        class="relative rounded-lg border bg-card cursor-pointer transition-colors duration-300 overflow-hidden group/card shadow-sm"
        :class="selection?.isSelected(String(row.id))
          ? 'border-primary ring-4 ring-primary/10 bg-primary/5'
          : 'border-border/40 hover:border-primary/30'"
        @click="onCardClick($event, row)"
      >
        <!-- Selection Checkbox -->
        <div
          v-if="selection"
          class="absolute top-4 left-4 z-20 transition-all duration-300 transform group-hover/card:scale-110"
          :class="selection.isSelected(String(row.id)) || hasSelection ? 'opacity-100 scale-100' : 'opacity-0 scale-75 group-hover/card:opacity-100'"
          @click="onCheckboxClick($event, row)"
        >
            <div
                class="size-7 rounded-lg border-2 flex items-center justify-center transition-colors shadow-sm"
                :class="selection.isSelected(String(row.id))
                    ? 'bg-primary border-primary text-primary-foreground'
                    : 'bg-background/90 border-border hover:border-primary/60 hover:bg-background'"
            >
                <Check v-if="selection.isSelected(String(row.id))" class="size-4 stroke-[4px]" />
            </div>
        </div>

        <!-- Thumbnail Area -->
        <div class="h-48 bg-muted/10 flex items-center justify-center overflow-hidden relative border-b border-border/10">
          <img
            v-if="imageField && row[imageField]"
            :src="String(row[imageField])"
            class="w-full h-full object-cover transition-transform duration-1000 group-hover/card:scale-110"
            :alt="formatCell(titleCol ? row[titleCol.key] : '')"
          />
          <div v-else class="flex flex-col items-center gap-3">
              <div class="size-16 rounded-lg bg-primary/5 flex items-center justify-center border border-primary/10 group-hover/card:border-primary/30 transition-colors">
                <ImageIcon class="size-8 text-primary/30 group-hover/card:text-primary/50 transition-colors" />
              </div>
              <span class="text-3xl font-semibold text-primary/5 opacity-40 group-hover/card:opacity-60 transition-opacity select-none tracking-widest">
                {{ titleCol ? String(formatCell(row[titleCol.key])).slice(0, 1).toUpperCase() : '?' }}
              </span>
          </div>
        </div>

        <!-- Card content -->
        <div class="p-6 space-y-4">
          <!-- Title Section -->
          <div v-if="titleCol" class="space-y-1">
              <div class="flex items-center justify-between">
                <span class="text-xs font-medium uppercase tracking-widest text-muted-foreground/40 leading-none">ID: {{ row.id }}</span>
                <div class="size-1.5 rounded-full bg-primary/20 group-hover/card:bg-primary transition-colors duration-500" />
              </div>
              <p class="font-semibold text-base text-foreground/90 leading-tight line-clamp-2 group-hover/card:text-primary transition-colors duration-300">
                {{ formatCell(row[titleCol.key]) }}
              </p>
          </div>

          <!-- Metadata Grid -->
          <div class="grid gap-2 pt-4 border-t border-border/10 group-hover/card:border-primary/10 transition-colors">
              <div v-for="col in bodyColumns" :key="col.key" class="flex items-center justify-between gap-4 min-w-0">
                <span class="text-xs font-medium text-muted-foreground/50 shrink-0 uppercase tracking-widest">{{ col.label }}</span>
                <span class="text-xs font-medium text-foreground/70 truncate">
                  <template v-if="getFieldType(col.key) === 'Date' || getFieldType(col.key) === 'Datetime'">
                    {{ formatDate(row[col.key], getFieldType(col.key)) }}
                  </template>
                  <template v-else-if="getFieldType(col.key) === 'Check'">
                      <Badge :variant="row[col.key] ? 'success' : 'secondary'" class="!text-xs !px-2 !py-0.5 !rounded-lg !font-semibold">
                          {{ row[col.key] ? 'ТАК' : 'НІ' }}
                      </Badge>
                  </template>
                  <template v-else>
                    {{ formatCell(row[col.key]) }}
                  </template>
                </span>
              </div>
          </div>
        </div>

        <!-- Hover Indicator Line -->
        <div class="absolute bottom-0 left-0 right-0 h-1 bg-primary transform scale-x-0 group-hover/card:scale-x-100 transition-transform duration-500 origin-center" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.gallery-view-container {
    animation: fadeIn 0.4s ease-out;
}

@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}
</style>
