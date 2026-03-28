<script setup lang="ts">
import { computed } from 'vue'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/spinner'
import {
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  FileX,
  Check as CheckIcon,
} from 'lucide-vue-next'
import type { DocField, DocTypeStatusConfig } from '@/types'
import type { ListColumn } from '@/core/composables/useListColumns'

const props = defineProps<{
  columns: ListColumn[]
  rows: Record<string, unknown>[]
  fields: DocField[]
  isLoading: boolean
  sortKey: string
  sortOrder: 'asc' | 'desc'
  selectedIds: string[]
  allSelected?: boolean
  statusConfig?: DocTypeStatusConfig | null
}>()

const emit = defineEmits<{
  sort: [key: string]
  select: [id: string]
  selectAll: []
  rowClick: [row: Record<string, unknown>]
}>()

const fieldMap = computed(() => {
  const m: Record<string, DocField> = {}
  for (const f of props.fields) m[f.fieldname] = f
  return m
})

function getFieldType(key: string): string {
  return fieldMap.value[key]?.fieldtype ?? 'Text'
}

// Status indicator lookup map (built from status_config)
const statusIndicatorMap = computed(() => {
  const m = new Map<string, { color: string; icon?: string | null; label?: string | null }>()
  if (!props.statusConfig?.indicators) return m
  for (const ind of props.statusConfig.indicators) {
    m.set(ind.value, ind)
  }
  return m
})

const statusFieldName = computed(() => props.statusConfig?.field ?? null)

// Color → Tailwind badge classes
const colorToBadge: Record<string, { variant: 'default' | 'secondary' | 'destructive' | 'outline'; class?: string }> = {
  gray: { variant: 'outline' },
  blue: { variant: 'default' },
  green: { variant: 'secondary' },
  yellow: { variant: 'outline', class: 'border-yellow-400 text-yellow-700 bg-yellow-50' },
  orange: { variant: 'outline', class: 'border-orange-400 text-orange-700 bg-orange-50' },
  red: { variant: 'destructive' },
  purple: { variant: 'outline', class: 'border-purple-400 text-purple-700 bg-purple-50' },
  pink: { variant: 'outline', class: 'border-pink-400 text-pink-700 bg-pink-50' },
}

function getStatusBadge(val: string, fieldname: string): { variant: 'default' | 'secondary' | 'destructive' | 'outline'; class?: string; label: string } {
  // Use configured indicator if this is the status field
  if (statusFieldName.value === fieldname) {
    const ind = statusIndicatorMap.value.get(val)
    if (ind) {
      const badge = colorToBadge[ind.color] ?? { variant: 'outline' as const }
      return { ...badge, label: ind.label ?? val }
    }
  }
  // Fallback: regex-based heuristic
  return { variant: selectVariantFallback(val), label: val }
}

function selectVariantFallback(val: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  const v = val.toLowerCase()
  if (/^(active|активн|відкри|новий|нова|нове|запущен|виконуєть|in.progress|open|new)/.test(v)) return 'default'
  if (/^(done|завершен|виконан|закрит|completed|закінчен|успішн|success)/.test(v)) return 'secondary'
  if (/^(cancel|скасован|відхил|помилк|error|fail|danger|blocked)/.test(v)) return 'destructive'
  return 'outline'
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

function formatCell(val: unknown): string {
  if (val === null || val === undefined || val === '') return '—'
  return String(val)
}

function isSelected(id: string) {
  return props.allSelected || props.selectedIds.includes(id)
}
</script>

<template>
  <!-- Loading -->
  <div v-if="isLoading && !rows.length" class="flex justify-center py-16">
    <Spinner size="lg" />
  </div>

  <!-- Table -->
  <div v-else class="border border-border rounded-lg overflow-hidden bg-card shadow-sm">
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-border bg-muted/50">
          <th class="w-10 px-3 py-3">
            <Checkbox
              :model-value="allSelected || (rows.length > 0 && selectedIds.length === rows.length)"
              @update:model-value="emit('selectAll')"
            />
          </th>
          <th
            v-for="col in columns"
            :key="col.key"
            class="text-left px-3 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground select-none transition-colors"
            :class="{ 'cursor-pointer hover:text-foreground': col.sortable }"
            @click="col.sortable && emit('sort', col.key)"
          >
            <span class="inline-flex items-center gap-1">
              {{ col.label }}
              <ArrowUp v-if="sortKey === col.key && sortOrder === 'asc'" class="size-3.5" />
              <ArrowDown v-else-if="sortKey === col.key && sortOrder === 'desc'" class="size-3.5" />
              <ArrowUpDown v-else-if="col.sortable" class="size-3.5 opacity-0 group-hover:opacity-30" />
            </span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="String(row.id)"
          class="border-b border-border last:border-0 hover:bg-muted/30 cursor-pointer transition-colors group"
          :class="{ 'bg-primary/5': isSelected(String(row.id)) }"
        >
          <td class="px-3 py-3" @click.stop>
            <Checkbox
              :model-value="isSelected(String(row.id))"
              @update:model-value="emit('select', String(row.id))"
            />
          </td>
          <td
            v-for="(col, ci) in columns"
            :key="col.key"
            class="px-3 py-3"
            @click="emit('rowClick', row)"
          >
            <!-- First column: bold primary link -->
            <template v-if="ci === 0">
              <span class="font-semibold text-primary hover:underline">
                {{ formatCell(row[col.key]) }}
              </span>
            </template>

            <!-- Check field: icon -->
            <template v-else-if="getFieldType(col.key) === 'Check'">
              <CheckIcon v-if="row[col.key]" class="size-4 text-emerald-500" />
              <span v-else class="text-muted-foreground/30">—</span>
            </template>

            <!-- Select / status field: colored badge -->
            <template v-else-if="getFieldType(col.key) === 'Select' || statusFieldName === col.key">
              <template v-if="row[col.key] !== null && row[col.key] !== undefined && row[col.key] !== ''">
                <Badge
                  :variant="getStatusBadge(String(row[col.key]), col.key).variant"
                  class="font-normal"
                  :class="getStatusBadge(String(row[col.key]), col.key).class"
                >
                  {{ getStatusBadge(String(row[col.key]), col.key).label }}
                </Badge>
              </template>
              <span v-else class="text-muted-foreground/30">—</span>
            </template>

            <!-- Date / Datetime: formatted -->
            <template v-else-if="getFieldType(col.key) === 'Date' || getFieldType(col.key) === 'Datetime'">
              <span class="text-muted-foreground tabular-nums">
                {{ formatDate(row[col.key], getFieldType(col.key)) }}
              </span>
            </template>

            <!-- Default -->
            <template v-else>
              <span class="text-muted-foreground">{{ formatCell(row[col.key]) }}</span>
            </template>
          </td>
        </tr>
        <!-- Empty state -->
        <tr v-if="!rows.length && !isLoading">
          <td :colspan="columns.length + 1" class="px-3 py-16 text-center">
            <div class="flex flex-col items-center gap-2">
              <FileX class="size-10 text-muted-foreground/40" />
              <p class="text-sm text-muted-foreground">Записів не знайдено</p>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
