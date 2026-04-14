<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import type { DocField } from '@/types'
import type { ListColumn } from '@/core/composables/useListColumns'
import { FileX } from '@lucide/vue'

const props = defineProps<{
  rows: Record<string, unknown>[]
  columns: ListColumn[]
  fields: DocField[]
  doctype: string
  workspace?: string
  isLoading?: boolean
}>()

const router = useRouter()

const fieldMap = computed(() => {
  const m: Record<string, DocField> = {}
  for (const f of props.fields) m[f.fieldname] = f
  return m
})

// Image field to use as card thumbnail
const imageField = computed<string | null>(() => {
  const f = props.fields.find(f => f.fieldtype === 'Image' || f.fieldtype === 'Attach')
  return f?.fieldname ?? null
})

// Primary title column (first visible column)
const titleCol = computed(() => props.columns[0] ?? null)

// Rest of visible columns (for card body), skip image field
const bodyColumns = computed(() =>
  props.columns.slice(1).filter(c => c.key !== imageField.value).slice(0, 4)
)

function navigateToDoc(row: Record<string, unknown>) {
  const ws = props.workspace ?? 'grunt'
  router.push(`/${ws}/list/${props.doctype}/${row.id}`)
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
  <!-- Empty state -->
  <div v-if="!isLoading && !rows.length" class="flex flex-col items-center gap-2 py-16 text-center">
    <FileX class="size-10 text-muted-foreground/40" />
    <p class="text-sm text-muted-foreground">Записів не знайдено</p>
  </div>

  <!-- Skeleton -->
  <div v-else-if="isLoading && !rows.length"
    class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
    <div v-for="i in 10" :key="i" class="rounded-lg border border-border bg-card p-4 space-y-2 animate-pulse">
      <div class="h-32 rounded-md bg-muted" />
      <div class="h-4 w-3/4 rounded bg-muted" />
      <div class="h-3 w-1/2 rounded bg-muted" />
    </div>
  </div>

  <!-- Gallery grid -->
  <div v-else class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
    <div
      v-for="row in rows"
      :key="String(row.id)"
      class="rounded-lg border border-border bg-card hover:shadow-md hover:border-primary/30 cursor-pointer transition-all duration-150 overflow-hidden group"
      @click="navigateToDoc(row)"
    >
      <!-- Thumbnail -->
      <div class="h-32 bg-muted/50 flex items-center justify-center overflow-hidden">
        <img
          v-if="imageField && row[imageField]"
          :src="String(row[imageField])"
          class="w-full h-full object-cover"
          :alt="formatCell(titleCol ? row[titleCol.key] : '')"
        />
        <span v-else class="text-3xl font-bold text-muted-foreground/20 uppercase select-none">
          {{ titleCol ? String(formatCell(row[titleCol.key])).slice(0, 2) : '?' }}
        </span>
      </div>

      <!-- Card body -->
      <div class="p-3 space-y-1.5">
        <!-- Title -->
        <p v-if="titleCol" class="font-semibold text-sm text-primary truncate group-hover:underline">
          {{ formatCell(row[titleCol.key]) }}
        </p>

        <!-- Additional fields -->
        <div v-for="col in bodyColumns" :key="col.key" class="flex items-baseline gap-1.5">
          <span class="text-[10px] text-muted-foreground shrink-0 uppercase tracking-wide">{{ col.label }}:</span>
          <span class="text-xs text-foreground/80 truncate">
            <template v-if="getFieldType(col.key) === 'Date' || getFieldType(col.key) === 'Datetime'">
              {{ formatDate(row[col.key], getFieldType(col.key)) }}
            </template>
            <template v-else>
              {{ formatCell(row[col.key]) }}
            </template>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
