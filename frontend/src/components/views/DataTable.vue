<script setup lang="ts">
import { computed, ref, nextTick, shallowRef } from 'vue'
import type { Component } from 'vue'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
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
  hideHeader?: boolean
  hideBody?: boolean
}>()

const emit = defineEmits<{
  sort: [key: string]
  select: [id: string]
  selectAll: []
  rowClick: [row: Record<string, unknown>]
  inlineUpdate: [rowId: string, field: string, value: string]
}>()

// ── Inline editing ────────────────────────────────────────────────────────
interface InlineEdit { rowId: string; field: string; value: string }
const inlineEdit = ref<InlineEdit | null>(null)
const inlineInput = ref<HTMLInputElement | null>(null)

const INLINE_SKIP = new Set(['Check', 'Select', 'Date', 'Datetime', 'Image', 'Attach', 'RichText', 'JSON', 'Code', 'Signature', 'Link', 'Rating', 'Icon'])

function canInlineEdit(fieldtype: string): boolean {
  return !INLINE_SKIP.has(fieldtype)
}

async function startEdit(row: Record<string, unknown>, field: string, fieldtype: string) {
  if (!canInlineEdit(fieldtype)) return
  inlineEdit.value = { rowId: String(row.id), field, value: String(row[field] ?? '') }
  await nextTick()
  inlineInput.value?.focus()
  inlineInput.value?.select()
}

function commitEdit() {
  if (!inlineEdit.value) return
  emit('inlineUpdate', inlineEdit.value.rowId, inlineEdit.value.field, inlineEdit.value.value)
  inlineEdit.value = null
}

function cancelEdit() {
  inlineEdit.value = null
}

function isEditing(rowId: string, field: string): boolean {
  return inlineEdit.value?.rowId === rowId && inlineEdit.value?.field === field
}

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
  blue: { variant: 'outline', class: 'border-blue-400 text-blue-700 bg-blue-50' },
  green: { variant: 'outline', class: 'border-green-500 text-green-700 bg-green-50' },
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
  return { variant: 'outline', label: val }
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

// ── Icon field ────────────────────────────────────────────────────────────────
type IconMap = Record<string, Component>
const lucideIcons = shallowRef<IconMap>({})
let iconsLoaded = false

function loadIcons() {
  if (iconsLoaded) return
  iconsLoaded = true
  import('lucide-vue-next').then((lib) => { lucideIcons.value = lib as unknown as IconMap })
}

function getIconComponent(name: string): Component | null {
  loadIcons()
  if (!name) return null
  const pascal = name.includes('-')
    ? name.split('-').map(s => s.charAt(0).toUpperCase() + s.slice(1)).join('')
    : name
  return (lucideIcons.value[pascal] ?? null) as Component | null
}
</script>

<template>
  <!-- Skeleton loading (first load — no rows yet) -->
  <div v-if="isLoading && !rows.length" class="overflow-hidden rounded-md border">
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-border bg-muted/50">
          <th class="w-10 px-3 py-3">
            <Skeleton class="h-4 w-4" />
          </th>
          <th v-for="col in columns" :key="col.key" class="px-3 py-3">
            <Skeleton class="h-3 w-20" />
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="i in 8" :key="i" class="border-b border-border last:border-0">
          <td class="px-3 py-3">
            <Skeleton class="h-4 w-4" />
          </td>
          <td v-for="col in columns" :key="col.key" class="px-3 py-3">
            <Skeleton class="h-4" :class="col === columns[0] ? 'w-32' : 'w-20'" />
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- Table -->
  <div v-else class="overflow-hidden rounded-xl border border-border/60 bg-card shadow-sm">
    <table class="w-full text-sm">
      <thead v-if="!hideHeader">
        <tr class="border-b border-border/40 bg-muted/40 backdrop-blur-sm">
          <th class="w-10 px-4 py-3.5">
            <Checkbox :model-value="allSelected || (rows.length > 0 && selectedIds.length === rows.length)"
              @update:model-value="emit('selectAll')" class="bg-background" />
          </th>
          <th v-for="col in columns" :key="col.key"
            class="text-left px-4 py-3.5 text-[11px] font-bold uppercase tracking-[0.1em] text-muted-foreground/80 select-none transition-colors"
            :class="{ 'cursor-pointer hover:text-foreground group/th': col.sortable }"
            @click="col.sortable && emit('sort', col.key)">
            <span class="inline-flex items-center gap-1">
              {{ col.label }}
              <ArrowUp v-if="sortKey === col.key && sortOrder === 'asc'" class="size-3.5 text-primary" />
              <ArrowDown v-else-if="sortKey === col.key && sortOrder === 'desc'" class="size-3.5 text-primary" />
              <ArrowUpDown v-else-if="col.sortable" class="size-3.5 opacity-0 group-hover/th:opacity-40 transition-opacity" />
            </span>
          </th>
        </tr>
      </thead>
      <tbody v-if="!hideBody">
        <tr v-for="row in rows" :key="String(row.id)"
          class="border-b border-border/30 last:border-0 hover:bg-muted/40 cursor-pointer transition-all duration-200 group relative"
          :class="{ 'bg-primary/[0.03] hover:bg-primary/[0.05]': isSelected(String(row.id)) }">
          
          <!-- Selected active indicator -->
          <td v-if="isSelected(String(row.id))" class="absolute left-0 top-0 bottom-0 w-0.5 bg-primary rounded-r-full pointer-events-none" />
          
          <td class="px-4 py-3" @click.stop>
            <Checkbox :model-value="isSelected(String(row.id))" @update:model-value="emit('select', String(row.id))"
              class="transition-transform duration-200" :class="{ 'scale-110': isSelected(String(row.id)) }" />
          </td>
          <td v-for="(col, ci) in columns" :key="col.key" class="px-4 py-3 text-[13px]"
            @click="!isEditing(String(row.id), col.key) && emit('rowClick', row)"
            @dblclick.stop="ci > 0 && startEdit(row, col.key, getFieldType(col.key))">
            <!-- Inline edit input -->
            <template v-if="isEditing(String(row.id), col.key)">
              <input
                ref="inlineInput"
                v-model="inlineEdit!.value"
                class="w-full rounded-md border border-primary px-2 py-1 text-sm bg-background shadow-sm focus:outline-none focus:ring-2 focus:ring-primary/20 transition-shadow"
                @blur="commitEdit"
                @keydown.enter.prevent="commitEdit"
                @keydown.escape.prevent="cancelEdit"
                @click.stop
              />
            </template>

            <!-- First column: bold primary link -->
            <template v-else-if="ci === 0">
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
                <Badge :variant="getStatusBadge(String(row[col.key]), col.key).variant" class="font-normal"
                  :class="getStatusBadge(String(row[col.key]), col.key).class">
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

            <!-- Geolocation: lat, lng -->
            <template v-else-if="getFieldType(col.key) === 'Geolocation'">
              <template v-if="row[col.key] && typeof row[col.key] === 'object'">
                <span class="tabular-nums text-muted-foreground font-mono text-xs">
                  {{ Number((row[col.key] as any).lat).toFixed(5) }},
                  {{ Number((row[col.key] as any).lng).toFixed(5) }}
                </span>
              </template>
              <span v-else class="text-muted-foreground/30">—</span>
            </template>

            <!-- Rating field: star display -->
            <template v-else-if="getFieldType(col.key) === 'Rating'">
              <template v-if="row[col.key] !== null && row[col.key] !== undefined && row[col.key] !== ''">
                <span class="inline-flex items-center gap-0.5">
                  <template v-for="i in 5" :key="i">
                    <svg v-if="Number(row[col.key]) >= i" xmlns="http://www.w3.org/2000/svg" class="size-3.5 text-amber-400" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
                    </svg>
                    <svg v-else-if="Number(row[col.key]) >= i - 0.5" xmlns="http://www.w3.org/2000/svg" class="size-3.5" viewBox="0 0 24 24">
                      <defs><linearGradient :id="`hstar-${String(row.id)}-${i}`"><stop offset="50%" stop-color="#fbbf24"/><stop offset="50%" stop-color="#d1d5db"/></linearGradient></defs>
                      <path :fill="`url(#hstar-${String(row.id)}-${i})`" d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
                    </svg>
                    <svg v-else xmlns="http://www.w3.org/2000/svg" class="size-3.5 text-gray-200" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
                    </svg>
                  </template>
                  <span class="ml-1 text-xs text-muted-foreground tabular-nums">{{ Number(row[col.key]).toFixed(1).replace(/\.0$/, '') }}</span>
                </span>
              </template>
              <span v-else class="text-muted-foreground/30">—</span>
            </template>

            <!-- Icon field: render lucide icon -->
            <template v-else-if="getFieldType(col.key) === 'Icon'">
              <template v-if="row[col.key]">
                <span class="inline-flex items-center gap-1.5 text-foreground/80">
                  <component :is="getIconComponent(String(row[col.key]))" v-if="getIconComponent(String(row[col.key]))" class="size-4 shrink-0" />
                  <span class="text-xs text-muted-foreground">{{ row[col.key] }}</span>
                </span>
              </template>
              <span v-else class="text-muted-foreground/30">—</span>
            </template>

            <!-- Link field: show __label if resolved, fallback to raw value -->
            <template v-else-if="getFieldType(col.key) === 'Link'">
              <span v-if="row[col.key] !== null && row[col.key] !== undefined && row[col.key] !== ''" class="text-foreground/90 font-medium">
                {{ (row[col.key + '__label'] as string) || formatCell(row[col.key]) }}
              </span>
              <span v-else class="text-muted-foreground/30">—</span>
            </template>

            <!-- Default -->
            <template v-else>
              <span class="text-foreground/90 font-medium">{{ formatCell(row[col.key]) }}</span>
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
