<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, watch, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import api from '@/core/api/client'
import { metaApi } from '@/core/api/meta'
import { reportsApi } from '@/core/api/reports'
import type { ReportChartConfig, ReportChartType } from '@/types'
import {
    Plus, Search, Save, Play, Trash2, ChevronRight,
    Layout, Table as TableIcon, FileBarChart, Pencil, ChartColumn, ListFilter, ArrowDownUp
} from '@lucide/vue'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'

const { t } = useI18n()

const props = defineProps<{
    workspaceName: string
    reportName?: string
}>()

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const previewLoading = ref(false)
const doctypes = ref<any[]>([])
const selectedDoctype = ref('')
const fields = ref<any[]>([])
const reportTitle = ref(props.reportName || t('New report'))

/** Internal doctype id (`name`) of the report being edited — resolved from
 *  `reportsApi.get()` by `report_name`, needed for the PUT call on save. */
const reportDocName = ref<string | null>(null)
const columns = ref<any[]>([]) // { fieldname, label, aggregation, fieldtype }
const filterConfigs = ref<any[]>([]) // { fieldname, label, fieldtype } — whitelist of fields the viewer can filter on
const chartEnabled = ref(false)
const chart = ref<ReportChartConfig>({ type: 'bar', label_field: '', value_fields: [], stacked: false })
const CHART_TYPES: { value: ReportChartType; label: string }[] = [
    { value: 'bar', label: t('Bar') },
    { value: 'line', label: t('Line') },
    { value: 'area', label: t('Area') },
    { value: 'pie', label: t('Pie') },
    { value: 'donut', label: t('Donut') },
]
function toggleChartValueField(fieldname: string) {
    const i = chart.value.value_fields.indexOf(fieldname)
    if (i >= 0) chart.value.value_fields.splice(i, 1)
    else chart.value.value_fields.push(fieldname)
}
// Fixed conditions, sort and "top N" (List-report options, see grunt/reports/list_options.py)
interface Condition { fieldname: string; op: string; value: string }
const conditions = ref<Condition[]>([])
const sortBy = ref('')
const sortOrder = ref<'asc' | 'desc'>('asc')
const rowLimit = ref<number | undefined>(undefined)
const OPERATORS = [
    { value: '=', label: '=' },
    { value: '!=', label: '≠' },
    { value: '>', label: '>' },
    { value: '<', label: '<' },
    { value: '>=', label: '≥' },
    { value: '<=', label: '≤' },
    { value: 'like', label: t('contains') },
    { value: 'not like', label: t('does not contain') },
    { value: 'in', label: t('one of (comma-separated)') },
    { value: 'not in', label: t('none of') },
    { value: 'is set', label: t('is set') },
    { value: 'is not set', label: t('is empty') },
]
const NO_VALUE_OPS = new Set(['is set', 'is not set'])
const DATE_GROUPS = [
    { value: 'none', label: t('Exact date') },
    { value: 'day', label: t('By day') },
    { value: 'month', label: t('By month') },
    { value: 'quarter', label: t('By quarter') },
    { value: 'year', label: t('By year') },
]
function isDateColumn(col: any) {
    return col.fieldtype === 'Date' || col.fieldtype === 'Datetime'
}
function addCondition() {
    conditions.value.push({ fieldname: '', op: '=', value: '' })
}
function removeCondition(index: number) {
    conditions.value.splice(index, 1)
}
const listOptions = computed(() => ({
    conditions: conditions.value.filter(c => c.fieldname),
    sort_by: sortBy.value || null,
    sort_order: sortOrder.value,
    row_limit: rowLimit.value || null,
}))

const previewData = ref<any[]>([])
const previewCols = ref<any[]>([])
const previewMeta = ref<any>(null)

const AGGREGATIONS = [
    { value: 'none', label: t('None') },
    { value: 'sum', label: t('Sum (SUM)') },
    { value: 'count', label: t('Count (COUNT)') },
    { value: 'avg', label: t('Average (AVG)') },
    { value: 'min', label: t('Minimum (MIN)') },
    { value: 'max', label: t('Maximum (MAX)') },
]

onMounted(async () => {
    doctypes.value = (await metaApi.list()).filter(dt => !dt.is_child)

    // Auto-select from query
    if (route.query.doctype) {
        selectedDoctype.value = route.query.doctype as string
    }

    if (props.reportName && props.reportName !== 'new') {
        const rep = await reportsApi.get(props.reportName)
        reportDocName.value = rep.name
        selectedDoctype.value = rep.doctype ?? ''
        columns.value = rep.columns ?? []
        filterConfigs.value = Array.isArray(rep.filters_config) ? rep.filters_config as any[] : []
        if (rep.chart_config && rep.chart_config.type) {
            chartEnabled.value = true
            chart.value = {
                type: rep.chart_config.type,
                label_field: rep.chart_config.label_field ?? '',
                value_fields: Array.isArray(rep.chart_config.value_fields) ? [...rep.chart_config.value_fields] : [],
                stacked: !!rep.chart_config.stacked,
                color: rep.chart_config.color,
            }
        }
        conditions.value = (rep.conditions ?? []).map((c) => ({ fieldname: c.fieldname, op: c.op, value: String(c.value ?? '') }))
        sortBy.value = rep.sort_by ?? ''
        sortOrder.value = rep.sort_order === 'desc' ? 'desc' : 'asc'
        rowLimit.value = rep.row_limit || undefined
        reportTitle.value = rep.report_name
    }
})

watch(selectedDoctype, async (name) => {
    if (!name) return
    const dt = await metaApi.get(name)
    fields.value = dt.fields
    // Reset columns if doctype changed
    if (columns.value.length === 0 || columns.value[0].doctype !== name) {
        // keep columns if we are editing an existing report
    }
})

function addColumn(field: any) {
    if (columns.value.find(c => c.fieldname === field.fieldname)) return
    columns.value.push({
        fieldname: field.fieldname,
        label: field.label,
        fieldtype: field.fieldtype,
        aggregation: 'none'
    })
}

function removeColumn(index: number) {
    columns.value.splice(index, 1)
}

function addFilter(fieldname: string) {
    const field = fields.value.find(f => f.fieldname === fieldname)
    if (!field || filterConfigs.value.some(f => f.fieldname === fieldname)) return
    filterConfigs.value.push({
        fieldname: field.fieldname,
        label: field.label,
        fieldtype: field.fieldtype,
    })
}

function removeFilter(index: number) {
    filterConfigs.value.splice(index, 1)
}

async function runPreview() {
    if (!selectedDoctype.value || columns.value.length === 0) return

    previewLoading.value = true
    try {
        const res = await api.post('/api/v1/method/grunt.reports.doctypes.Report.report.preview', {
            doctype: selectedDoctype.value,
            columns: columns.value,
            filters: {},
            ...listOptions.value,
        })
        previewData.value = res.data.data.data
        previewCols.value = res.data.data.columns
        previewMeta.value = res.data.data.meta
    } finally {
        previewLoading.value = false
    }
}

async function saveReport() {
    if (!reportTitle.value || !selectedDoctype.value) {
        alert(t('Enter a name and a document type'))
        return
    }

    loading.value = true
    try {
        const payload = {
            report_name: reportTitle.value,
            doctype: selectedDoctype.value,
            report_type: 'List',
            columns: columns.value,
            filters_config: filterConfigs.value,
            chart_config: chartEnabled.value && chart.value.label_field ? chart.value : null,
            ...listOptions.value,
        }

        if (reportDocName.value) {
            await reportsApi.update(reportDocName.value, payload)
        } else {
            await reportsApi.create(payload)
        }

        router.push({ name: 'workspace-report', params: { workspaceName: props.workspaceName, reportName: reportTitle.value } })
    } finally {
        loading.value = false
    }
}

const filteredFields = ref('')
const displayFields = computed(() => {
    if (!filteredFields.value) return fields.value
    return fields.value.filter(f =>
        f.label.toLowerCase().includes(filteredFields.value.toLowerCase()) ||
        f.fieldname.toLowerCase().includes(filteredFields.value.toLowerCase())
    )
})
</script>

<template>
    <div class="flex h-screen overflow-hidden bg-background">
        <!-- Sidebar: Configuration -->
        <aside class="w-[400px] border-r flex flex-col bg-card shrink-0 shadow-sm z-20">
            <div class="p-6 border-b space-y-4">
                <div class="space-y-1.5">
                    <label class="font-semibold uppercase tracking-widest text-muted-foreground">{{ t('Report name') }}</label>
                    <div class="relative">
                        <FileBarChart class="absolute left-2.5 top-1/2 -translate-y-1/2 size-4 text-primary pointer-events-none" />
                        <Input v-model="reportTitle" :placeholder="t('Report name')"
                            class="!pl-8 !pr-8 font-semibold text-base h-9" />
                        <Pencil class="absolute right-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground pointer-events-none" />
                    </div>
                </div>

                <div class="space-y-2">
                    <label class="font-semibold uppercase tracking-widest text-muted-foreground">{{ t('Document type') }}</label>
                    <Select v-model="selectedDoctype">
                      <SelectTrigger class="w-full">
                        <SelectValue :placeholder="t('Choose a DocType')" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem v-for="opt in doctypes" :key="opt.name" :value="opt.name">{{ opt.label }}</SelectItem>
                      </SelectContent>
                    </Select>
                </div>
            </div>

            <!-- Fields & Columns Tabs -->
            <Tabs default-value="columns" class="flex-1 flex flex-col overflow-hidden">
                <TabsList class="w-full h-auto justify-start rounded-none border-b border-border bg-transparent">
                    <TabsTrigger value="columns" class="flex-1">{{ t('Columns') }}</TabsTrigger>
                </TabsList>

                <TabsContent value="columns" class="flex-1 overflow-y-auto p-4 space-y-6 focus-visible:ring-0 m-0">
                    <!-- Selected Columns -->
                    <div class="space-y-3">
                        <div class="flex items-center justify-between">
                            <h4 class="font-semibold uppercase text-muted-foreground flex items-center gap-1.5">
                                <TableIcon class="size-3.5" />
                                {{ t('Selected columns') }} ({{ columns.length }})
                            </h4>
                        </div>

                        <div v-if="columns.length === 0"
                            class="border-2 border-dashed rounded-lg p-8 text-center text-muted-foreground bg-muted/20">
                            {{ t('Add fields from the list below') }}
                        </div>

                        <div v-for="(col, index) in columns" :key="col.fieldname"
                            class="group flex flex-col gap-2 p-3 rounded-lg border bg-background hover:border-primary/30 transition-all shadow-sm">
                            <div class="flex items-center justify-between">
                                <div class="flex items-center gap-2 min-w-0">
                                    <Badge
                                        class="h-5 px-1.5 text-xs font-semibold uppercase opacity-50 shrink-0">{{
                                            col.fieldtype }}</Badge>
                                    <span class="font-semibold truncate">{{ col.label }}</span>
                                </div>
                                <button @click="removeColumn(index)"
                                    class="opacity-0 group-hover:opacity-100 p-1 text-muted-foreground hover:text-destructive transition-all">
                                    <Trash2 class="size-4" />
                                </button>
                            </div>

                            <div class="flex items-center gap-2">
                                <Select v-model="col.aggregation">
                                  <SelectTrigger class="h-7 text-xs w-full">
                                    <SelectValue :placeholder="t('Aggregation')" />
                                  </SelectTrigger>
                                  <SelectContent>
                                    <SelectItem v-for="opt in AGGREGATIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
                                  </SelectContent>
                                </Select>
                                <label class="flex items-center gap-1.5 text-muted-foreground whitespace-nowrap cursor-pointer select-none">
                                    <input type="checkbox" v-model="col.total" class="size-3.5 accent-primary" />
                                    {{ t('Subtotal') }}
                                </label>
                            </div>
                            <Select v-if="isDateColumn(col) && (!col.aggregation || col.aggregation === 'none')"
                                :model-value="col.date_group || 'none'"
                                @update:model-value="v => (col.date_group = v === 'none' ? undefined : v)">
                                <SelectTrigger class="h-7 text-xs w-full">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem v-for="g in DATE_GROUPS" :key="g.value" :value="g.value">{{ g.label }}</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>

                    <!-- Fixed conditions -->
                    <div v-if="selectedDoctype" class="space-y-3">
                        <h4 class="font-semibold uppercase text-muted-foreground flex items-center gap-1.5">
                            <ListFilter class="size-3.5" />
                            {{ t('Conditions') }} ({{ conditions.length }})
                        </h4>
                        <p class="text-muted-foreground">
                            {{ t('Always applied to the report. For dates you can write today, today-30, today+7.') }}
                        </p>
                        <div v-for="(cond, i) in conditions" :key="i" class="flex flex-col gap-2 p-2 rounded-lg border bg-background">
                            <div class="flex items-center gap-2">
                                <Select v-model="cond.fieldname">
                                    <SelectTrigger class="h-7 text-xs flex-1"><SelectValue :placeholder="t('Field')" /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem v-for="f in fields" :key="f.fieldname" :value="f.fieldname">{{ f.label }}</SelectItem>
                                    </SelectContent>
                                </Select>
                                <button @click="removeCondition(i)" class="p-1 text-muted-foreground hover:text-destructive transition-colors">
                                    <Trash2 class="size-4" />
                                </button>
                            </div>
                            <div class="flex items-center gap-2">
                                <Select v-model="cond.op">
                                    <SelectTrigger class="h-7 text-xs w-36"><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem v-for="o in OPERATORS" :key="o.value" :value="o.value">{{ o.label }}</SelectItem>
                                    </SelectContent>
                                </Select>
                                <Input v-if="!NO_VALUE_OPS.has(cond.op)" v-model="cond.value" :placeholder="t('Value')" class="h-7 text-xs flex-1" />
                            </div>
                        </div>
                        <Button variant="outline" size="sm" class="w-full" @click="addCondition">
                            <Plus class="size-4" /> {{ t('Add condition') }}
                        </Button>
                    </div>

                    <!-- Sort & top N -->
                    <div v-if="selectedDoctype && columns.length" class="space-y-3">
                        <h4 class="font-semibold uppercase text-muted-foreground flex items-center gap-1.5">
                            <ArrowDownUp class="size-3.5" />
                            {{ t('Sorting') }}
                        </h4>
                        <div class="flex items-center gap-2">
                            <Select :model-value="sortBy || 'default'" @update:model-value="v => (sortBy = v === 'default' ? '' : String(v))">
                                <SelectTrigger class="h-7 text-xs flex-1"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="default">{{ t('By grouping') }}</SelectItem>
                                    <SelectItem v-for="c in columns" :key="c.fieldname" :value="c.fieldname">{{ c.label }}</SelectItem>
                                </SelectContent>
                            </Select>
                            <Select v-model="sortOrder" :disabled="!sortBy">
                                <SelectTrigger class="h-7 text-xs w-32"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="asc">{{ t('Ascending') }}</SelectItem>
                                    <SelectItem value="desc">{{ t('Descending') }}</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div class="flex items-center gap-2">
                            <span class="text-muted-foreground whitespace-nowrap">{{ t('Show the first') }}</span>
                            <Input v-model.number="rowLimit" type="number" min="1" :placeholder="t('all')" class="h-7 text-xs w-24" />
                            <span class="text-muted-foreground">{{ t('rows') }}</span>
                        </div>
                    </div>

                    <!-- Filters whitelist -->
                    <div v-if="selectedDoctype" class="space-y-3">
                        <h4 class="font-semibold uppercase text-muted-foreground flex items-center gap-1.5">
                            <Search class="size-3.5" />
                            {{ t('Filters') }} ({{ filterConfigs.length }})
                        </h4>
                        <p class="text-muted-foreground">
                            {{ t('Fields the report viewer can filter by (the operator and value are chosen in the report itself).') }}
                        </p>
                        <div v-for="(flt, i) in filterConfigs" :key="flt.fieldname"
                            class="flex items-center justify-between gap-2 p-2 rounded-lg border bg-background">
                            <span class="flex items-center gap-2 min-w-0">
                                <Badge class="h-5 px-1.5 text-xs font-semibold uppercase opacity-50 shrink-0">{{ flt.fieldtype }}</Badge>
                                <span class="truncate">{{ flt.label }}</span>
                            </span>
                            <button @click="removeFilter(i)"
                                class="p-1 text-muted-foreground hover:text-destructive transition-colors">
                                <Trash2 class="size-4" />
                            </button>
                        </div>
                        <Select :model-value="''" @update:model-value="v => addFilter(String(v))">
                            <SelectTrigger class="h-8 text-xs w-full">
                                <SelectValue :placeholder="t('+ Add filter field')" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem v-for="f in fields" :key="f.fieldname" :value="f.fieldname"
                                    :disabled="filterConfigs.some(x => x.fieldname === f.fieldname)">
                                    {{ f.label }}
                                </SelectItem>
                            </SelectContent>
                        </Select>
                    </div>

                    <!-- Chart -->
                    <div v-if="selectedDoctype" class="space-y-3">
                        <label class="flex items-center gap-2 font-semibold uppercase text-muted-foreground cursor-pointer">
                            <input type="checkbox" v-model="chartEnabled" class="accent-primary size-3.5" />
                            <ChartColumn class="size-3.5" />
                            {{ t('Chart') }}
                        </label>

                        <div v-if="chartEnabled" class="space-y-3 pl-1">
                            <Select v-model="chart.type">
                                <SelectTrigger class="h-8 text-xs w-full"><SelectValue :placeholder="t('Chart type')" /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem v-for="t in CHART_TYPES" :key="t.value" :value="t.value">{{ t.label }}</SelectItem>
                                </SelectContent>
                            </Select>

                            <Select v-model="chart.label_field">
                                <SelectTrigger class="h-8 text-xs w-full"><SelectValue :placeholder="t('Label column (X axis)')" /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem v-for="c in columns" :key="c.fieldname" :value="c.fieldname">{{ c.label }}</SelectItem>
                                </SelectContent>
                            </Select>

                            <div>
                                <p class="text-muted-foreground mb-1.5">{{ t('Value columns') }}</p>
                                <div class="flex flex-wrap gap-1.5">
                                    <button v-for="c in columns" :key="c.fieldname" type="button"
                                        class="px-2 py-1 rounded-md border transition-colors"
                                        :class="chart.value_fields.includes(c.fieldname)
                                            ? 'bg-primary text-primary-foreground border-primary'
                                            : 'bg-background hover:bg-muted'"
                                        :disabled="c.fieldname === chart.label_field"
                                        :title="c.fieldname === chart.label_field ? t('This is the label column') : ''"
                                        @click="toggleChartValueField(c.fieldname)">
                                        {{ c.label }}
                                    </button>
                                </div>
                            </div>

                            <label v-if="chart.type === 'bar'"
                                class="flex items-center gap-2 text-muted-foreground cursor-pointer">
                                <input type="checkbox" v-model="chart.stacked" class="accent-primary size-3.5" />
                                {{ t('Stacked') }}
                            </label>
                        </div>
                    </div>

                    <!-- Available Fields -->
                    <div v-if="selectedDoctype" class="space-y-3">
                        <h4 class="font-semibold uppercase text-muted-foreground flex items-center gap-1.5">
                            <Plus class="size-3.5" />
                            {{ t('Available fields') }}
                        </h4>
                        <div class="relative">
                            <Search class="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground z-10" />
                            <Input v-model="filteredFields" :placeholder="t('Search fields...')"
                                class="!h-9 !pl-8 !text-xs !bg-muted/20 !border-none !w-full" />
                        </div>
                        <div class="grid grid-cols-1 gap-1">
                            <button v-for="f in displayFields" :key="f.fieldname"
                                class="flex items-center justify-between px-3 py-2 rounded-lg text-left hover:bg-muted text-foreground/80 group transition-colors"
                                @click="addColumn(f)" :disabled="columns.some(c => c.fieldname === f.fieldname)"
                                :class="{ 'opacity-50 cursor-not-allowed': columns.some(c => c.fieldname === f.fieldname) }">
                                <div class="flex flex-col min-w-0">
                                    <span class="font-medium truncate">{{ f.label }}</span>
                                    <span class="text-muted-foreground">{{ f.fieldname }}</span>
                                </div>
                                <Plus class="size-4 opacity-0 group-hover:opacity-100 text-primary transition-all" />
                            </button>
                        </div>
                    </div>
                </TabsContent>
            </Tabs>

            <!-- Sidebar Footer -->
            <div class="p-4 border-t flex flex-col gap-2 bg-muted/10">
                <Button variant="secondary" :disabled="previewLoading || !selectedDoctype || columns.length === 0" @click="runPreview" class="w-full h-10 font-semibold">
                    <Play v-if="!previewLoading" class="size-4 mr-2" />
                    <Spinner v-else class="!size-4 !mr-2" />
                    {{ t('Preview') }}
                </Button>
                <div class="flex gap-2">
                    <Button :disabled="loading || columns.length === 0" @click="saveReport"
                        class="flex-1 h-10 font-semibold">
                        <Save class="size-4 mr-2" />
                        {{ t('Save') }}
                    </Button>
                    <Button variant="outline" class="h-10 px-3" @click="router.back()">{{ t('Cancel') }}</Button>
                </div>
            </div>
        </aside>

        <!-- Main: Preview -->
        <main class="flex-1 flex flex-col bg-muted/10 overflow-hidden">
            <!-- Tools -->
            <header class="p-8 pb-4 flex justify-between items-center shrink-0">
                <div class="flex items-center gap-2 text-muted-foreground/80 font-medium">
                    <span>{{ t('Reports') }}</span>
                    <ChevronRight class="size-3 opacity-50" />
                    <span class="text-foreground font-semibold">{{ reportTitle }}</span>
                </div>
            </header>

            <div class="flex-1 px-8 pb-8 overflow-hidden flex flex-col">
                <div v-if="previewCols.length === 0 && !previewLoading"
                    class="flex-1 flex flex-col items-center justify-center p-12 text-center rounded-lg border-2 border-dashed bg-card/30">
                    <div class="size-16 rounded-full bg-primary/5 flex items-center justify-center mb-4">
                        <Layout class="size-8 text-primary/40" />
                    </div>
                    <h3 class="text-xl font-semibold mb-2">{{ t('Set up the report') }}</h3>
                    <p class="text-muted-foreground max-w-sm mb-6">{{ t('Choose a DocType and add columns in the side panel to see the result.') }}</p>
                    <Button variant="outline" @click="selectedDoctype = doctypes[0]?.name" v-if="!selectedDoctype">{{ t('Choose the first available DocType') }}</Button>
                </div>

                <div v-else class="flex-1 bg-card rounded-lg border shadow-sm overflow-hidden flex flex-col">
                    <!-- Table Toolbar -->
                    <div class="p-4 border-b flex items-center justify-between bg-muted/20 shrink-0">
                        <div
                            class="flex items-center gap-4 font-semibold text-muted-foreground uppercase tracking-widest">
                            <span class="flex items-center gap-1.5">
                                <TableIcon class="size-3.5" /> {{ t('Result') }}
                            </span>
                            <span v-if="previewMeta">{{ t('{n} rows').replace('{n}', String(previewMeta.rows)) }}</span>
                            <span v-if="previewMeta">{{ previewMeta.time_ms }} {{ t('ms') }}</span>
                        </div>
                        <div v-if="previewLoading" class="flex items-center gap-2">
                            <Spinner class="!size-4" />
                            <span
                                class="font-semibold text-primary italic uppercase anima">{{ t('Loading...') }}</span>
                        </div>
                    </div>

                    <!-- Results Table -->
                    <div class="flex-1 overflow-auto">
                        <table class="w-full">
                            <thead class="sticky top-0 bg-background/95 z-10">
                                <tr class="border-b shadow-sm">
                                    <th v-for="col in previewCols" :key="col.fieldname"
                                        class="px-4 py-3 text-left font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">
                                        {{ col.label }}
                                    </th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr v-if="previewLoading && previewData.length === 0" v-for="i in 10" :key="i"
                                    class="border-b last:border-0 opacity-50">
                                    <td v-for="colIdx in previewCols.length || 5" :key="colIdx" class="px-4 py-4">
                                        <Skeleton class="h-4 w-full" />
                                    </td>
                                </tr>
                                <tr v-else v-for="(row, ri) in previewData" :key="ri"
                                    class="border-b last:border-0 hover:bg-muted/30 transition-colors">
                                    <td v-for="col in previewCols" :key="col.fieldname"
                                        class="px-4 py-3 text-foreground/90 font-medium whitespace-nowrap">
                                        {{ row[col.fieldname] === null || row[col.fieldname] === undefined ? '—' :
                                            row[col.fieldname] }}
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </main>
    </div>
</template>

<style scoped>
/* Hide scrollbar but keep functionality */
.scrollbar-none::-webkit-scrollbar {
  display: none;
}
.scrollbar-none {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
</style>
