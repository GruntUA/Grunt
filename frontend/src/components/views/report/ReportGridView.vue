<script setup lang="ts">
import { computed, watch, ref, onMounted } from 'vue'
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
  FileSpreadsheet,
  FileBarChart2,
  Save,
} from '@lucide/vue'
import draggable from 'vuedraggable'
import type { DocType, DocField, ActiveFilter, ReportSummary } from '@/types'
import type { ListColumn } from '@/core/composables/useListColumns'
import { getListCell } from '@/core/listCellRegistry'
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
import { useReportModel, isNumericField, type AggFn } from './useReportModel'

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
  fetchNextPage?: () => void
  hasNextPage?: boolean
  isFetchingNextPage?: boolean
  refreshKey: number
}>()

const emit = defineEmits<{
  sort: [key: string]
  'row-click': [row: Record<string, unknown>]
}>()

// ── Full load (opt-in) ──────────────────────────────────────────────────────
// The list query is paginated for infinite scroll. Pulling every page can mean
// dozens of sequential requests, so it is off by default: subtotals cover the
// rows already loaded, and "Завантажити всі" pumps the rest on demand.
const MAX_AUTOLOAD = 20_000
const loadAll = ref(false)

watch(
  () => [loadAll.value, props.hasNextPage, props.isFetchingNextPage, props.rows.length],
  () => {
    if (!loadAll.value || !props.fetchNextPage) return
    if (props.hasNextPage && !props.isFetchingNextPage && props.rows.length < MAX_AUTOLOAD) {
      props.fetchNextPage()
    }
  },
  { immediate: true },
)
// A refresh or DocType switch drops back to the lazy default.
watch(() => [props.doctype, props.refreshKey], () => { loadAll.value = false })

const isPartial = computed(() => !!props.hasNextPage)
const truncated = computed(() => props.hasNextPage && props.rows.length >= MAX_AUTOLOAD)

// ── Model ───────────────────────────────────────────────────────────────────
const model = useReportModel({
  doctype: () => props.doctype,
  dt: () => props.dt,
  listColumns: () => props.listColumns,
  rows: () => props.rows,
})

const statusConfig = computed(() => statusConfigOf(props.dt))
const normalizedSortKey = computed(() => props.sortKey || '')

// ── Saved `Report` (type=List) round-trip ───────────────────────────────────
const router = useRouter()
const auth = useAuthStore()
const dialog = useDialog()
const toast = useToast()

const canSave = computed(() => !!auth.user?.is_superadmin)
const savedReports = ref<ReportSummary[]>([])

async function loadSavedReports() {
  try {
    const all = await reportsApi.list()
    savedReports.value = all.filter(
      (r) => r.report_type === 'List' && r.doctype === props.doctype,
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
  const name = (await dialog.prompt('Назва звіту'))?.trim()
  if (!name) return
  const { columns, droppedColumns } = model.toReportColumns()
  if (!columns.length) {
    toast.warning('Додайте хоча б одну колонку')
    return
  }
  try {
    await reportsApi.create({
      report_name: name,
      doctype: props.doctype,
      report_type: 'List',
      columns,
      filters_config: buildFiltersConfig(),
    })
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Не вдалося зберегти звіт')
    return
  }
  if (droppedColumns.length) {
    toast.info(`Не включено (потребують агрегації): ${droppedColumns.join(', ')}`)
  }
  toast.success('Звіт збережено', 'Готово', {
    action: {
      label: 'Відкрити',
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
    toast.success(`Застосовано «${rep.report_name}»`)
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Не вдалося відкрити звіт')
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

// ── Formatting ──────────────────────────────────────────────────────────────
const nf = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 })
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
  none: 'Без підсумку',
  sum: 'Сума',
  avg: 'Середнє',
  min: 'Мінімум',
  max: 'Максимум',
  count: 'Кількість',
}
const AGG_CHOICES: AggFn[] = ['sum', 'avg', 'min', 'max', 'count', 'none']

function groupLabelText(key: string): string {
  if (!key || key === 'null' || key === 'undefined') return 'Без значення'
  if (model.groupField.value?.fieldtype === 'Check') {
    return key === '1' || key === 'true' ? 'Так' : 'Ні'
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

// ── CSV export of the rendered grid ─────────────────────────────────────────
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
      lines.push(csvCell(`${model.groupField.value?.label ?? 'Група'}: ${groupLabelText(g.key)}`))
      pushRows(g.rows)
      if (model.hasAnyAggregate.value) lines.push(totalLine('Підсумок', g.aggregates))
    }
  } else {
    pushRows(props.rows)
  }
  if (model.hasAnyAggregate.value) lines.push(totalLine('Разом', model.grandTotals.value))

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
            Стовпці
            <span class="tabular-nums text-muted-foreground">{{ model.visibleColumns.value.length }}</span>
          </Button>
        </PopoverTrigger>
        <PopoverContent class="w-64 p-1" align="start">
          <div class="px-2 py-1.5 text-xs font-medium text-muted-foreground">Стовпці звіту</div>
          <div class="max-h-[320px] overflow-y-auto scrollbar-none py-1">
            <draggable :model-value="model.visibleColumns.value" item-key="key" handle=".drag-handle"
              class="space-y-0.5" @end="(e: any) => model.reorderColumns(e.oldIndex, e.newIndex)">
              <template #item="{ element: col }">
                <div class="flex items-center gap-2 p-2 rounded-md hover:bg-accent hover:text-accent-foreground cursor-pointer"
                  @click="model.toggleColumn(col.key)">
                  <span class="drag-handle cursor-grab text-muted-foreground select-none">⠿</span>
                  <Check class="size-4 shrink-0" />
                  <span class="flex-1 truncate">{{ col.label }}</span>
                </div>
              </template>
            </draggable>
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
            {{ model.groupField.value ? model.groupField.value.label : 'Групувати' }}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" class="max-h-[320px] overflow-y-auto">
          <DropdownMenuItem @click="model.setGroupBy(null)">
            <Check class="size-4" :class="{ invisible: model.groupKey.value }" />
            <span>Без групування</span>
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
            Звіти
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" class="w-64 max-h-[360px] overflow-y-auto">
          <DropdownMenuLabel class="text-xs text-muted-foreground">
            Збережені звіти для «{{ dt?.label ?? doctype }}»
          </DropdownMenuLabel>
          <template v-if="savedReports.length">
            <DropdownMenuItem v-for="r in savedReports" :key="r.name" @click="openSavedReport(r)">
              <FileBarChart2 class="size-4 text-muted-foreground" />
              <span class="flex-1 truncate">{{ r.report_name }}</span>
            </DropdownMenuItem>
          </template>
          <div v-else class="px-2 py-2 text-xs text-muted-foreground">Ще немає</div>
          <template v-if="canSave">
            <DropdownMenuSeparator />
            <DropdownMenuItem @click="saveAsReport">
              <Save class="size-4" />
              <span>Зберегти поточний як звіт…</span>
            </DropdownMenuItem>
          </template>
        </DropdownMenuContent>
      </DropdownMenu>

      <Button variant="outline" size="sm" class="gap-1.5" @click="exportCsv">
        <Download class="size-4" />
        Експорт CSV
      </Button>
    </div>

    <div v-if="isPartial" class="flex items-center gap-2 text-xs text-muted-foreground">
      <template v-if="truncated">
        <span class="text-amber-600 dark:text-amber-500">
          Досягнуто ліміту {{ MAX_AUTOLOAD.toLocaleString('uk-UA') }} записів — підсумки лише за ними.
        </span>
      </template>
      <template v-else-if="loadAll">
        <span class="size-3 rounded-full border-2 border-muted border-t-primary animate-spin" />
        Завантаження всіх записів… {{ rows.length.toLocaleString('uk-UA') }} / {{ (meta?.total ?? 0).toLocaleString('uk-UA') }}
      </template>
      <template v-else>
        <span>
          Підсумки за {{ rows.length.toLocaleString('uk-UA') }}
          {{ meta ? `з ${meta.total.toLocaleString('uk-UA')}` : '' }} завантаженими.
        </span>
        <Button variant="link" size="sm" class="h-auto p-0 text-xs" @click="loadAll = true">
          Завантажити всі
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
            <TableCell :colspan="model.visibleColumns.value.length" class="px-3 py-16 text-center border-0">
              <div class="flex flex-col items-center gap-2">
                <FileSpreadsheet class="size-8 text-muted-foreground/40" />
                <p class="text-muted-foreground">Записів не знайдено</p>
              </div>
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
                    <a v-if="ci === 0 && rowHref(row)" :href="rowHref(row)!"
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
                    <span v-if="ci === 0" class="text-muted-foreground">Підсумок</span>
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
                <a v-if="ci === 0 && rowHref(row)" :href="rowHref(row)!"
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
              <span v-if="ci === 0">Разом{{ meta ? ` (${rows.length}/${meta.total})` : '' }}</span>
              <span v-else-if="col.key in model.grandTotals.value">{{ fmtNum(model.grandTotals.value[col.key]) }}</span>
            </TableCell>
          </TableRow>
        </TableFooter>
      </Table>
    </div>

    <div v-if="isFetchingNextPage" class="flex justify-center py-2">
      <div class="size-4 rounded-full border-2 border-muted border-t-primary animate-spin" />
    </div>
  </div>
</template>
