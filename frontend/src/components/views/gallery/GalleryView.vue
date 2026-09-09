<script setup lang="ts">
import { computed } from 'vue'
import { formatDate as fmtDate, formatDateTime as fmtDateTime } from '@/core/datetime'
import { useRouter } from 'vue-router'
import type { DocField } from '@/types'
import type { ListColumn } from '@/core/composables/useListColumns'

import { FileX, ImageIcon } from '@lucide/vue'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'

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

function navigateToDoc(row: Record<string, unknown>) {
  const ws = props.workspace ?? 'grunt'
  router.push(`/${ws}/${props.doctype}/${row.id}`)
}

function formatCell(val: unknown): string {
  if (val === null || val === undefined || val === '') return '—'
  return String(val)
}

// Link/relation fields carry a resolved display label under the `<field>__label` key
function displayValue(row: Record<string, unknown>, key: string): string {
  const label = row[`${key}__label`]
  return formatCell(label ?? row[key])
}

function getFieldType(key: string): string {
  return fieldMap.value[key]?.fieldtype ?? 'Text'
}

function formatDate(val: unknown, type: string): string {
  return type === 'Date' ? fmtDate(val as string) : fmtDateTime(val as string)
}
</script>

<template>
  <div class="min-h-64 px-1">
    <!-- Empty state -->
    <div v-if="!isLoading && !rows.length"
      class="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed py-16 text-center">
      <div class="flex size-10 items-center justify-center rounded-lg bg-muted">
        <FileX class="size-5 text-muted-foreground" />
      </div>
      <div class="space-y-1">
        <p class="text-sm font-medium">Записів не знайдено</p>
        <p class="mx-auto max-w-xs text-xs text-muted-foreground">
          Спробуйте змінити фільтри або додати новий документ
        </p>
      </div>
    </div>

    <!-- Skeleton -->
    <div v-else-if="isLoading && !rows.length"
      class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">
      <div v-for="i in 12" :key="i" class="overflow-hidden rounded-lg border bg-card">
        <Skeleton class="aspect-[4/3] !rounded-none" />
        <div class="space-y-2 p-3">
          <Skeleton class="h-3.5 w-4/5 rounded" />
          <Skeleton class="h-3 w-2/5 rounded" />
          <div class="space-y-1.5 pt-1">
            <Skeleton v-for="j in 2" :key="j" class="h-2.5 w-full rounded" />
          </div>
        </div>
      </div>
    </div>

    <!-- Gallery grid -->
    <div v-else
      class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">
      <div
        v-for="row in rows"
        :key="String(row.id)"
        class="group/card relative cursor-pointer overflow-hidden rounded-lg border bg-card shadow-sm transition-colors"
        :class="selection?.isSelected(String(row.id))
          ? 'border-primary ring-2 ring-primary'
          : 'hover:border-primary/40'"
        @click="onCardClick($event, row)"
      >
        <!-- Selection checkbox -->
        <div
          v-if="selection"
          class="absolute left-2 top-2 z-10 rounded bg-black/30 p-1 transition-opacity"
          :class="selection.isSelected(String(row.id)) || hasSelection
            ? 'opacity-100'
            : 'opacity-0 group-hover/card:opacity-100'"
          @click.stop
        >
          <Checkbox
            :model-value="selection.isSelected(String(row.id))"
            class="border-white/70 bg-transparent shadow-none"
            @update:model-value="selection.toggle(String(row.id))"
          />
        </div>

        <!-- Thumbnail -->
        <div class="flex aspect-[4/3] items-center justify-center overflow-hidden border-b bg-muted">
          <img
            v-if="imageField && row[imageField]"
            :src="String(row[imageField])"
            class="size-full object-contain p-2"
            :alt="formatCell(titleCol ? row[titleCol.key] : '')"
          />
          <ImageIcon v-else class="size-6 text-muted-foreground" />
        </div>

        <!-- Content -->
        <div class="space-y-2 p-3">
          <div v-if="titleCol" class="space-y-0.5">
            <span class="text-xs text-muted-foreground">ID: {{ row.id }}</span>
            <p class="line-clamp-2 text-sm font-medium leading-tight">
              {{ formatCell(row[titleCol.key]) }}
            </p>
          </div>

          <!-- Metadata -->
          <div v-if="bodyColumns.length" class="space-y-1 border-t pt-2">
            <div v-for="col in bodyColumns" :key="col.key" class="flex items-center justify-between gap-2 text-xs">
              <span class="shrink-0 text-muted-foreground">{{ col.label }}</span>
              <span class="truncate text-foreground">
                <template v-if="getFieldType(col.key) === 'Date' || getFieldType(col.key) === 'Datetime'">
                  {{ formatDate(row[col.key], getFieldType(col.key)) }}
                </template>
                <Badge v-else-if="getFieldType(col.key) === 'Check'"
                  :variant="row[col.key] ? 'default' : 'secondary'">
                  {{ row[col.key] ? 'ТАК' : 'НІ' }}
                </Badge>
                <template v-else>
                  {{ displayValue(row, col.key) }}
                </template>
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
