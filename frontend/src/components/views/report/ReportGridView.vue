<script setup lang="ts">
import { formatNumber } from '@/core/currency'
import { useI18n } from 'vue-i18n'
import { computed, watch, ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import {
  ChevronUp,
  ChevronDown,
  ArrowUpDown,
  ChevronRight,
  SlidersHorizontal,
  Check,
  Layers,
  Sigma,
  Download,
  FileBarChart2,
  Save,
} from '@lucide/vue'
import { VueDraggable } from 'vue-draggable-plus'
import type { DocType, DocField, ActiveFilter, ReportSummary } from '@/types'
import type { ListColumn } from '@/core/composables/useListColumns'
import { getListCell } from '@/core/listCellRegistry'
import { getAsyncFieldComponent, getNonPhysicalTypeSet } from '@/core/fieldRegistry'
import { docsApi } from '@/core/api/docs'
import DefaultListCell from '@/components/fields/Default/ListCell.vue'
import { statusConfigOf } from '@/core/status'
import { reportsApi } from '@/core/api/reports'
import { useAuthStore } from '@/stores/auth'
import { useDialog } from '@/core/composables/useDialog'
import { useToast } from '@/core/composables/useToast'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import ListEmptyState from '@/components/views/ListEmptyState.vue'
import { useReportModel, isNumericField, type AggFn } from './useReportModel'

const { t } = useI18n()

interface TableMeta { page: number; pages: number; total: number }

const props = defineProps<{
  dt: DocType | null
  workspace: string
  doctype: string
  rows: Record<string, unknown>[]
  listColumns: ListColumn[]
  fields: DocField[]
  activeFilters: ActiveFilter[]
  meta?: TableMeta
  isLoading: boolean
  hasData: boolean
  sortKey: string | null
  sortOrder: 'asc' | 'desc'
  perPage: number
  refreshKey: number
}>()

const emit = defineEmits<{
  sort: [key: string]
  'row-click': [row: Record<string, unknown>]
  'set-per-page': [n: number]
}>()

// Full load (opt-in)
// The list query returns one page at a time. Client-side subtotals only cover
// the current page, so "Завантажити всі" bumps the page size to pull the whole
// filtered set (capped) in a single request.
const MAX_AUTOLOAD = 20_000

const loadedAll = computed(() => props.perPage >= MAX_AUTOLOAD)
const isPartial = computed(() => props.rows.length < (props.meta?.total ?? 0))
const truncated = computed(() => loadedAll.value && isPartial.value)

function loadAll() {
  emit('set-per-page', Math.min(props.meta?.total ?? MAX_AUTOLOAD, MAX_AUTOLOAD))
}

// A refresh, DocType switch, or leaving the report view drops back to the lazy
// default so nothing else silently re-pulls tens of thousands of rows.
watch(() => [props.doctype, props.refreshKey], () => {
  if (loadedAll.value) emit('set-per-page', 20)
})
onBeforeUnmount(() => {
  if (loadedAll.value) emit('set-per-page', 20)
})

// Model
const model = useReportModel({
  doctype: () => props.doctype,
  dt: () => props.dt,
  listColumns: () => props.listColumns,
  rows: () => props.rows,
})

const statusConfig = computed(() => statusConfigOf(props.dt))
const normalizedSortKey = computed(() => props.sortKey || '')

// Saved `Report` (type=List) round-trip
const router = useRouter()
const auth = useAuthStore()
const dialog = useDialog()
const toast = useToast()

const canSave = computed(() => !!auth.isSystemManager)
const savedReports = ref<ReportSummary[]>([])

async function loadSavedReports() {
  try {
    const all = await reportsApi.list()
    savedReports.value = all.filter(
      (r) => r.report_type === 'List' && r.ref_doctype === props.doctype,
    )
  } catch {
    savedReports.value = []
  }
}
onMounted(loadSavedReports)
watch(() => props.doctype, loadSavedReports)

/** Whitelist of filter fields for the saved report, from the active filters. */
function buildFiltersConfig(): Array<{ fieldname: string; label: string; fieldtype: string }> {
  const seen = new Set<string>()
  const out: Array<{ fieldname: string; label: string; fieldtype: string }> = []
  for (const f of props.activeFilters ?? []) {
    if (seen.has(f.fieldname)) continue
    seen.add(f.fieldname)
    const df = model.fieldMap.value[f.fieldname]
    out.push({
      fieldname: f.fieldname,
      label: df?.label ?? f.fieldname,
      fieldtype: df?.fieldtype ?? 'Data',
    })
  }
  return out
}

async function saveAsReport() {
  const name = (await dialog.prompt(t('Report name')))?.trim()
  if (!name) return
  const { columns, droppedColumns } = model.toReportColumns()
  if (!columns.length) {
    toast.warning(t('Add at least one column'))
    return
  }
  try {
    await reportsApi.create({
      report_name: name,
      ref_doctype: props.doctype,
      report_type: 'List',
      columns,
      filters_config: buildFiltersConfig(),
    })
  } catch (e) {
    toast.error(e instanceof Error ? e.message : t('Could not save the report'))
    return
  }
  if (droppedColumns.length) {
    toast.info(t('Not included (need aggregation): {columns}', { columns: droppedColumns.join(', ') }))
  }
  toast.success(t('Report saved'), t('Done'), {
    action: {
      label: t('Open'),
      onClick: () => router.push({
        name: 'workspace-report',
        params: { workspaceName: props.workspace, reportName: name },
      }),
    },
  })
  await loadSavedReports()
}

async function openSavedReport(rep: ReportSummary) {
  try {
    const detail = await reportsApi.get(rep.report_name)
    model.applyReportColumns(detail.columns ?? [])
    collapsed.value = new Set()
    toast.success(t('Applied «{name}»', { name: rep.report_name }))
  } catch (e) {
    toast.error(e instanceof Error ? e.message : t('Could not open the report'))
  }
}

const collapsed = ref<Set<string>>(new Set())
function toggleGroup(key: string) {
  const next = new Set(collapsed.value)
  next.has(key) ? next.delete(key) : next.add(key)
  collapsed.value = next
}
// Reset collapse memory whenever the grouping field changes.
watch(() => model.groupKey.value, () => { collapsed.value = new Set() })

// Formatting
const nf = { format: (v: number) => formatNumber(v, { maximumFractionDigits: 2 }) }
function fmtNum(v: number | undefined): string {
  return v === undefined || !Number.isFinite(v) ? '' : nf.format(v)
}

function fieldOf(key: string): DocField {
  return model.fieldMap.value[key] ?? { fieldname: key, fieldtype: 'Data', label: key } as DocField
}

function isNumericKey(key: string): boolean {
  return isNumericField(fieldOf(key))
}

/** Body-cell classes: numeric columns stay on one line & right-aligned; text wraps. */
function cellClass(key: string): string {
  return isNumericKey(key)
    ? 'px-3 py-1.5 align-top text-right tabular-nums whitespace-nowrap'
    : 'px-3 py-1.5 align-top whitespace-normal break-words max-w-[16rem]'
}

const AGG_LABELS: Record<AggFn, string> = {
  none: t('No total'),
  sum: t('Sum'),
  avg: t('Average'),
  min: t('Minimum'),
  max: t('Maximum'),
  count: t('Count'),
}
const AGG_CHOICES: AggFn[] = ['sum', 'avg', 'min', 'max', 'count', 'none']

function groupLabelText(key: string): string {
  if (!key || key === 'null' || key === 'undefined') return t('No value')
  if (model.groupField.value?.fieldtype === 'Check') {
    return key === '1' || key === 'true' ? t('Yes') : t('No')
  }
  return key
}

function rowDocId(row: Record<string, unknown>): string {
  return String(row.id ?? row.name ?? '')
}
function rowHref(row: Record<string, unknown>): string | null {
  const id = rowDocId(row)
  return id ? `/app/${props.workspace}/${props.doctype}/${encodeURIComponent(id)}` : null
}
function onAnchorClick(e: MouseEvent, row: Record<string, unknown>) {
  if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
  e.preventDefault()
  emit('row-click', row)
}

// CSV export of the rendered grid
function csvCell(v: unknown): string {
  const s = v === null || v === undefined ? '' : String(v)
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}
function exportCsv() {
  const cols = model.visibleColumns.value
  const lines: string[] = []
  lines.push(cols.map((c) => csvCell(c.label)).join(','))

  const pushRows = (rows: Record<string, unknown>[]) => {
    for (const r of rows) lines.push(cols.map((c) => csvCell(r[c.key])).join(','))
  }
  const totalLine = (label: string, aggs: Record<string, number>) =>
    cols
      .map((c, i) => {
        if (i === 0) return csvCell(label)
        return c.key in aggs ? csvCell(nf.format(aggs[c.key])) : ''
      })
      .join(',')

  if (model.groups.value) {
    for (const g of model.groups.value) {
      lines.push(csvCell(`${model.groupField.value?.label ?? t('Group')}: ${groupLabelText(g.key)}`))
      pushRows(g.rows)
      if (model.hasAnyAggregate.value) lines.push(totalLine(t('Subtotal'), g.aggregates))
    }
  } else {
    pushRows(props.rows)
  }
  if (model.hasAnyAggregate.value) lines.push(totalLine(t('Total'), model.grandTotals.value))

  const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8;' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${props.doctype}-report.csv`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(a.href)
}

const colsOpen = ref(false)

// Inline editing (opt-in per field via `editable_in_grid`)
const NON_PHYSICAL = getNonPhysicalTypeSet()

const editableKeys = computed(() => {
  const s = new Set<string>()
  for (const col of model.visibleColumns.value) {
    const f = fieldOf(col.key)
    if (f.editable_in_grid && !f.read_only && !NON_PHYSICAL.has(f.fieldtype)) s.add(col.key)
  }
  return s
})

const editing = ref<{ id: string; key: string } | null>(null)
const draft = ref<unknown>(null)
const saving = ref(false)

function isEditing(row: Record<string, unknown>, key: string): boolean {
  return !!editing.value && editing.value.id === rowDocId(row) && editing.value.key === key
}
function startEdit(row: Record<string, unknown>, key: string) {
  if (!editableKeys.value.has(key)) return
  editing.value = { id: rowDocId(row), key }
  draft.value = row[key] ?? null
}
function cancelEdit() {
  editing.value = null
  draft.value = null
}
async function commitEdit(row: Record<string, unknown>, key: string) {
  if (!editing.value || saving.value) return
  const id = rowDocId(row)
  if (!id || draft.value === (row[key] ?? null)) {
    editing.value = null
    return
  }
  saving.value = true
  try {
    await docsApi.update(props.doctype, id, { [key]: draft.value })
    row[key] = draft.value
    editing.value = null
  } catch (e) {
    toast.error(e instanceof Error ? e.message : t('Could not save'))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <!-- Control strip -->
    <div class="flex flex-wrap items-center gap-2">
      <!-- Columns -->
      <Popover v-model:open="colsOpen">
        <PopoverTrigger as-child>
          <Button variant="outline" size="sm" class="gap-1.5"
            :class="model.isCustomized.value && 'bg-accent text-accent-foreground'">
            <SlidersHorizontal class="size-4" />
            {{ t('Columns') }}
            <span class="tabular-nums text-muted-foreground">{{ model.visibleColumns.value.length }}</span>
          </Button>
        </PopoverTrigger>
        <PopoverContent class="w-64 p-1" align="start">
          <div class="px-2 py-1.5 font-medium text-muted-foreground">{{ t('Report columns') }}</div>
          <div class="max-h-[320px] overflow-y-auto scrollbar-none py-1">
            <VueDraggable :model-value="model.visibleColumns.value" handle=".drag-handle"
              class="space-y-0.5" @end="(e: any) => model.reorderColumns(e.oldIndex, e.newIndex)">
              <div v-for="col in model.visibleColumns.value" :key="col.key"
                class="flex items-center gap-2 p-2 rounded-md hover:bg-accent hover:text-accent-foreground cursor-pointer"
                @click="model.toggleColumn(col.key)">
                <span class="drag-handle cursor-grab text-muted-foreground select-none">⠿</span>
                <Check class="size-4 shrink-0" />
                <span class="flex-1 truncate">{{ col.label }}</span>
              </div>
            </VueDraggable>
            <div v-for="col in model.availableColumns.value.filter((c) => !model.isVisible(c.key))" :key="col.key"
              class="flex items-center gap-2 p-2 rounded-md hover:bg-accent hover:text-accent-foreground cursor-pointer"
              @click="model.toggleColumn(col.key)">
              <span class="size-4" />
              <Check class="size-4 shrink-0 invisible" />
              <span class="flex-1 truncate text-muted-foreground">{{ col.label }}</span>
            </div>
          </div>
        </PopoverContent>
      </Popover>

      <!-- Group by -->
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <Button variant="outline" size="sm" class="gap-1.5"
            :class="model.groupKey.value && 'bg-accent text-accent-foreground'">
            <Layers class="size-4" />
            {{ model.groupField.value ? model.groupField.value.label : t('Group') }}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" class="max-h-[320px] overflow-y-auto">
          <DropdownMenuItem @click="model.setGroupBy(null)">
            <Check class="size-4" :class="{ invisible: model.groupKey.value }" />
            <span>{{ t('No grouping') }}</span>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem v-for="f in model.groupableFields.value" :key="f.fieldname"
            @click="model.setGroupBy(f.fieldname)">
            <Check class="size-4" :class="{ invisible: model.groupKey.value !== f.fieldname }" />
            <span>{{ f.label }}</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <!-- Saved reports (round-trip with the Report DocType) -->
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <Button variant="outline" size="sm" class="gap-1.5 ml-auto">
            <FileBarChart2 class="size-4" />
            {{ t('Reports') }}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" class="w-64 max-h-[360px] overflow-y-auto">
          <DropdownMenuLabel class="text-xs text-muted-foreground">
            {{ t('Saved reports for «{doctype}»', { doctype: dt?.label ?? doctype }) }}
          </DropdownMenuLabel>
          <template v-if="savedReports.length">
            <DropdownMenuItem v-for="r in savedReports" :key="r.name" @click="openSavedReport(r)">
              <FileBarChart2 class="size-4 text-muted-foreground" />
              <span class="flex-1 truncate">{{ r.report_name }}</span>
            </DropdownMenuItem>
          </template>
          <div v-else class="px-2 py-2 text-muted-foreground">{{ t('None yet') }}</div>
          <template v-if="canSave">
            <DropdownMenuSeparator />
            <DropdownMenuItem @click="saveAsReport">
              <Save class="size-4" />
              <span>{{ t('Save current as report…') }}</span>
            </DropdownMenuItem>
          </template>
        </DropdownMenuContent>
      </DropdownMenu>

      <Button variant="outline" size="sm" class="gap-1.5" @click="exportCsv">
        <Download class="size-4" />
        {{ t('Export CSV') }}
      </Button>
    </div>

    <div v-if="isPartial" class="flex items-center gap-2 text-muted-foreground">
      <template v-if="truncated">
        <span class="text-amber-600 dark:text-amber-500">
          {{ t('Limit of {n} records reached — totals cover only these.', { n: formatNumber(MAX_AUTOLOAD) }) }}
        </span>
      </template>
      <template v-else>
        <span>
          {{ t('Totals for the current page') }} ({{ formatNumber(rows.length) }}{{ meta ? ` / ${formatNumber(meta.total)}` : '' }}).
        </span>
        <Button variant="link" size="sm" class="h-auto p-0 text-xs" @click="loadAll()">
          {{ t('Calculate for all') }}
        </Button>
      </template>
    </div>

    <!-- Grid -->
    <div class="bg-card rounded-lg ring-1 ring-border/60 overflow-x-auto">
      <Table class="w-full text-xs">
        <TableHeader>
          <TableRow class="hover:bg-transparent border-0">
            <TableHead v-for="col in model.visibleColumns.value" :key="col.key"
              class="px-3 py-2 font-semibold border-b border-border/40 align-bottom"
              :class="[
                normalizedSortKey === col.key ? 'text-foreground' : 'text-muted-foreground',
                isNumericKey(col.key) ? 'text-right' : 'text-left',
              ]">
              <div class="flex items-start gap-1" :class="isNumericKey(col.key) && 'justify-end'">
                <span class="inline-flex items-start gap-1 cursor-pointer select-none hover:text-foreground/80"
                  role="button" @click="emit('sort', col.key)">
                  <span class="break-words">{{ col.label }}</span>
                  <ChevronUp v-if="normalizedSortKey === col.key && sortOrder === 'asc'" class="size-3" />
                  <ChevronDown v-else-if="normalizedSortKey === col.key" class="size-3" />
                  <ArrowUpDown v-else class="size-3 opacity-40" />
                </span>
                <!-- Per-column aggregate picker (numeric only) -->
                <DropdownMenu v-if="isNumericField(fieldOf(col.key))">
                  <DropdownMenuTrigger as-child>
                    <button class="inline-flex items-center rounded p-0.5 hover:bg-accent"
                      :class="model.aggFor(col.key) !== 'none' ? 'text-primary' : 'text-muted-foreground/50'"
                      :title="AGG_LABELS[model.aggFor(col.key)]">
                      <Sigma class="size-3" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem v-for="fn in AGG_CHOICES" :key="fn" @click="model.setAgg(col.key, fn)">
                      <Check class="size-4" :class="{ invisible: model.aggFor(col.key) !== fn }" />
                      <span>{{ AGG_LABELS[fn] }}</span>
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </TableHead>
          </TableRow>
        </TableHeader>

        <TableBody>
          <!-- Loading -->
          <template v-if="isLoading && !rows.length">
            <TableRow v-for="i in 10" :key="i" class="border-b border-border/20 last:border-0">
              <TableCell :colspan="model.visibleColumns.value.length" class="px-3 py-2">
                <Skeleton class="h-4" />
              </TableCell>
            </TableRow>
          </template>

          <!-- Empty -->
          <TableRow v-else-if="!isLoading && !rows.length">
            <TableCell :colspan="model.visibleColumns.value.length" class="border-0 p-0">
              <ListEmptyState class="py-16" />
            </TableCell>
          </TableRow>

          <!-- Grouped -->
          <template v-else-if="model.groups.value">
            <template v-for="g in model.groups.value" :key="g.key">
              <TableRow class="bg-muted/30 border-b border-border/30 cursor-pointer hover:bg-muted/50"
                @click="toggleGroup(g.key)">
                <TableCell :colspan="model.visibleColumns.value.length" class="px-3 py-2">
                  <div class="flex items-center gap-2 font-medium">
                    <ChevronRight class="size-3.5 transition-transform" :class="!collapsed.has(g.key) && 'rotate-90'" />
                    <span class="text-muted-foreground/70 uppercase tracking-wide text-[0.7rem]">
                      {{ model.groupField.value?.label }}
                    </span>
                    <span>{{ groupLabelText(g.key) }}</span>
                    <span class="text-muted-foreground tabular-nums">· {{ g.rows.length }}</span>
                  </div>
                </TableCell>
              </TableRow>

              <template v-if="!collapsed.has(g.key)">
                <TableRow v-for="(row, ri) in g.rows" :key="rowDocId(row) || ri"
                  class="border-b border-border/10 cursor-pointer hover:bg-primary/5"
                  @click="emit('row-click', row)">
                  <TableCell v-for="(col, ci) in model.visibleColumns.value" :key="col.key" :class="cellClass(col.key)">
                    <div v-if="editableKeys.has(col.key) && isEditing(row, col.key)"
                      @click.stop @focusout="commitEdit(row, col.key)">
                      <component :is="getAsyncFieldComponent(fieldOf(col.key).fieldtype)"
                        :field="fieldOf(col.key)" :model-value="draft" autofocus
                        @update:model-value="draft = $event"
                        @keydown.enter.prevent="commitEdit(row, col.key)"
                        @keydown.esc.prevent="cancelEdit()" />
                    </div>
                    <button v-else-if="editableKeys.has(col.key)" type="button"
                      class="block w-full text-left rounded px-1 -mx-1 min-h-[1.5rem] hover:bg-accent/60"
                      @click.stop="startEdit(row, col.key)">
                      <component :is="getListCell(fieldOf(col.key).fieldtype) ?? DefaultListCell"
                        :value="row[col.key]" :row="row" :field="fieldOf(col.key)" :status-config="statusConfig" />
                    </button>
                    <a v-else-if="ci === 0 && rowHref(row)" :href="rowHref(row)!"
                      class="font-medium text-primary hover:underline" @click.stop="onAnchorClick($event, row)">
                      <component :is="getListCell(fieldOf(col.key).fieldtype) ?? DefaultListCell"
                        :value="row[col.key]" :row="row" :field="fieldOf(col.key)" :status-config="statusConfig" />
                    </a>
                    <component v-else :is="getListCell(fieldOf(col.key).fieldtype) ?? DefaultListCell"
                      :value="row[col.key]" :row="row" :field="fieldOf(col.key)" :status-config="statusConfig" />
                  </TableCell>
                </TableRow>

                <TableRow v-if="model.hasAnyAggregate.value" class="border-b border-border/30 bg-background/60">
                  <TableCell v-for="(col, ci) in model.visibleColumns.value" :key="col.key"
                    class="px-3 py-1.5 font-medium tabular-nums"
                    :class="isNumericKey(col.key) ? 'text-right whitespace-nowrap' : 'whitespace-normal'">
                    <span v-if="ci === 0" class="text-muted-foreground">{{ t('Subtotal') }}</span>
                    <span v-else-if="col.key in g.aggregates">{{ fmtNum(g.aggregates[col.key]) }}</span>
                  </TableCell>
                </TableRow>
              </template>
            </template>
          </template>

          <!-- Flat -->
          <template v-else>
            <TableRow v-for="(row, ri) in rows" :key="rowDocId(row) || ri"
              class="border-b border-border/10 cursor-pointer hover:bg-primary/5"
              @click="emit('row-click', row)">
              <TableCell v-for="(col, ci) in model.visibleColumns.value" :key="col.key" :class="cellClass(col.key)">
                <div v-if="editableKeys.has(col.key) && isEditing(row, col.key)"
                  @click.stop @focusout="commitEdit(row, col.key)">
                  <component :is="getAsyncFieldComponent(fieldOf(col.key).fieldtype)"
                    :field="fieldOf(col.key)" :model-value="draft" autofocus
                    @update:model-value="draft = $event"
                    @keydown.enter.prevent="commitEdit(row, col.key)"
                    @keydown.esc.prevent="cancelEdit()" />
                </div>
                <button v-else-if="editableKeys.has(col.key)" type="button"
                  class="block w-full text-left rounded px-1 -mx-1 min-h-[1.5rem] hover:bg-accent/60"
                  @click.stop="startEdit(row, col.key)">
                  <component :is="getListCell(fieldOf(col.key).fieldtype) ?? DefaultListCell"
                    :value="row[col.key]" :row="row" :field="fieldOf(col.key)" :status-config="statusConfig" />
                </button>
                <a v-else-if="ci === 0 && rowHref(row)" :href="rowHref(row)!"
                  class="font-medium text-primary hover:underline" @click.stop="onAnchorClick($event, row)">
                  <component :is="getListCell(fieldOf(col.key).fieldtype) ?? DefaultListCell"
                    :value="row[col.key]" :row="row" :field="fieldOf(col.key)" :status-config="statusConfig" />
                </a>
                <component v-else :is="getListCell(fieldOf(col.key).fieldtype) ?? DefaultListCell"
                  :value="row[col.key]" :row="row" :field="fieldOf(col.key)" :status-config="statusConfig" />
              </TableCell>
            </TableRow>
          </template>
        </TableBody>

        <TableFooter v-if="model.hasAnyAggregate.value && rows.length" class="border-t-2 border-border/60">
          <TableRow class="hover:bg-transparent">
            <TableCell v-for="(col, ci) in model.visibleColumns.value" :key="col.key"
              class="px-3 py-2 font-semibold tabular-nums"
              :class="isNumericKey(col.key) ? 'text-right whitespace-nowrap' : 'whitespace-normal'">
              <span v-if="ci === 0">{{ t('Total') }}{{ meta ? ` (${rows.length}/${meta.total})` : '' }}</span>
              <span v-else-if="col.key in model.grandTotals.value">{{ fmtNum(model.grandTotals.value[col.key]) }}</span>
            </TableCell>
          </TableRow>
        </TableFooter>
      </Table>
    </div>
  </div>
</template>
