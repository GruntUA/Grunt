<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { formatDate, formatDateTime } from '@/core/datetime'
import { useRouter } from 'vue-router'
import { reportsApi } from '@/core/api/reports'
import { metaApi } from '@/core/api/meta'
import { useAuthStore } from '@/stores/auth'
import type { ActiveFilter, DocField, ReportChartConfig } from '@/types'
import { Download, RefreshCw, Settings2, FileBarChart2, FileX, ImageDown } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import FilterBar from '@/components/views/FilterBar.vue'
import ReportChart from '@/components/reports/ReportChart.vue'

/** Frontend display operator → backend filter-key suffix (see grunt/db/api.py build_clauses). */
const OP_SUFFIX: Record<string, string> = {
    '=': '', '!=': '__ne', 'like': '__like',
    '>': '__gt', '<': '__lt', '>=': '__gte', '<=': '__lte', 'child_of': '__child_of',
}

const props = defineProps<{
    workspaceName: string
    reportName: string
}>()

const auth = useAuthStore()
const router = useRouter()

const report = ref<any>(null)
const data = ref<any[]>([])
const columns = ref<any[]>([])
const loading = ref(false)
const meta = ref<any>(null)
const filters = ref<Record<string, any>>({})
const filterFields = ref<DocField[]>([])
let filterFieldsLoaded = false

const chartConfig = computed<ReportChartConfig | null>(() => {
    const c = report.value?.chart_config
    return c && c.type && c.label_field ? c as ReportChartConfig : null
})
const viewMode = ref<'table' | 'chart' | 'both'>('table')
watch(chartConfig, (c) => { viewMode.value = c ? 'both' : 'table' })

const chartRef = ref<InstanceType<typeof ReportChart> | null>(null)
function exportChartPng() {
    const url = chartRef.value?.toPng()
    if (!url) return
    const a = document.createElement('a')
    a.href = url
    a.download = `${report.value?.report_name || 'report'}.png`
    a.click()
}

async function loadFilterFields() {
    filterFieldsLoaded = true
    const cfg = report.value?.filters_config
    const doctype = report.value?.doctype
    if (!Array.isArray(cfg) || cfg.length === 0 || !doctype) {
        filterFields.value = []
        return
    }
    try {
        const dt = await metaApi.get(doctype)
        const wanted = new Set(cfg.map((c: any) => c.fieldname))
        filterFields.value = (dt.fields ?? [])
            .filter((f) => wanted.has(f.fieldname))
            .map((f) => ({ ...f, in_filter: true }))
    } catch {
        filterFields.value = []
    }
}

function onFiltersChange(active: ActiveFilter[]) {
    const next: Record<string, any> = {}
    for (const f of active) {
        if (f.value === '' || f.value == null) continue
        next[`${f.fieldname}${OP_SUFFIX[f.op] ?? ''}`] = f.value
    }
    filters.value = next
    fetchReport()
}

async function fetchReport() {
    loading.value = true
    try {
        // 1. Fetch metadata
        report.value = await reportsApi.get(props.reportName)
        if (!filterFieldsLoaded) await loadFilterFields()

        // 2. Run report
        const runRes = await reportsApi.run(props.reportName, filters.value)
        data.value = runRes.data
        columns.value = runRes.columns
        meta.value = runRes.meta
    } finally {
        loading.value = false
    }
}

onMounted(fetchReport)
watch(() => props.reportName, () => {
    filterFieldsLoaded = false
    filters.value = {}
    fetchReport()
})

function formatCell(val: any, fieldtype: string): string {
    if (val === null || val === undefined || val === '') return '—'
    if (fieldtype === 'Date') return formatDate(val)
    if (fieldtype === 'Datetime') return formatDateTime(val)
    if (fieldtype === 'Float' || fieldtype === 'Int') return val.toLocaleString('uk-UA')
    return String(val)
}

function openBuilder() {
    router.push({ name: 'report-builder', params: { workspaceName: props.workspaceName, reportName: props.reportName } })
}
</script>

<template>
    <div class="flex flex-col gap-6 p-8">
        <!-- Header -->
        <div class="flex items-end justify-between gap-4">
            <div>
                <h2 class="text-2xl font-semibold tracking-tight text-foreground flex items-center gap-2">
                    <FileBarChart2 class="size-6 text-primary" />
                    {{ report?.report_name || reportName }}
                </h2>
                <div class="flex items-center gap-2 mt-1">
                    <Badge variant="secondary" class="font-normal">{{ report?.report_type }}</Badge>
                    <p class="text-muted-foreground" v-if="meta">
                        {{ meta.rows }} записів • {{ meta.time_ms }}мс
                    </p>
                </div>
            </div>
            
            <div class="flex items-center gap-2">
                <div v-if="chartConfig" class="flex rounded-md border overflow-hidden mr-1 text-xs font-medium">
                    <button
                        v-for="m in ([['table', 'Таблиця'], ['chart', 'Графік'], ['both', 'Обидва']] as const)"
                        :key="m[0]"
                        class="px-2.5 py-1.5 transition-colors"
                        :class="viewMode === m[0] ? 'bg-primary text-primary-foreground' : 'bg-card hover:bg-muted text-muted-foreground'"
                        @click="viewMode = m[0]">
                        {{ m[1] }}
                    </button>
                </div>
                <Button v-if="chartConfig && viewMode !== 'table'" variant="outline" size="sm" @click="exportChartPng">
                    <ImageDown class="size-4 mr-2" />
                    PNG
                </Button>
                <Button variant="outline" size="sm" @click="fetchReport" :disabled="loading">
                    <RefreshCw class="size-4 mr-2" :class="{ 'animate-spin': loading }" />
                    Оновити
                </Button>
                <Button variant="outline" size="sm" as="a" :href="reportsApi.exportXlsxUrl(reportName)" download>
                    <Download class="size-4 mr-2" />
                    XLSX
                </Button>
                <Button size="sm" @click="openBuilder" v-if="auth.user?.is_superadmin">
                    <Settings2 class="size-4 mr-2" />
                    Конструктор
                </Button>
            </div>
        </div>

        <!-- Filters -->
        <div v-if="filterFields.length" class="p-3 rounded-lg border bg-card/50">
            <FilterBar
                :fields="filterFields"
                :doctype="report?.doctype || undefined"
                @change="onFiltersChange"
            />
        </div>

        <!-- Chart -->
        <div v-if="chartConfig && viewMode !== 'table'" class="border rounded-lg shadow-sm bg-card p-4">
            <ReportChart v-if="data.length" ref="chartRef" :config="chartConfig" :columns="columns" :data="data" />
            <div v-else class="h-[360px] flex items-center justify-center text-muted-foreground">
                Дані відсутні
            </div>
        </div>

        <!-- Table -->
        <div v-show="viewMode !== 'chart'" class="border rounded-lg overflow-hidden shadow-sm bg-card">
            <div class="overflow-x-auto">
                <table class="w-full">
                    <thead>
                        <tr class="border-b bg-muted/30">
                            <th v-for="col in columns" :key="col.fieldname" class="px-4 py-3 text-left font-semibold text-muted-foreground uppercase tracking-wider text-xs">
                                {{ col.label }}
                            </th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr v-if="loading && data.length === 0" v-for="i in 5" :key="i" class="border-b last:border-0">
                            <td v-for="col in columns.length || 5" :key="col" class="px-4 py-4">
                                <Skeleton class="h-4 w-full" />
                            </td>
                        </tr>
                        <tr v-else-if="data.length === 0" class="h-64">
                            <td :colspan="columns.length" class="text-center py-12">
                                <div class="flex flex-col items-center gap-2 text-muted-foreground">
                                    <FileX class="size-12 opacity-20" />
                                    <p>Дані відсутні</p>
                                </div>
                            </td>
                        </tr>
                        <tr v-else v-for="(row, ri) in data" :key="ri" class="border-b last:border-0 hover:bg-muted/30 transition-colors">
                            <td v-for="col in columns" :key="col.fieldname" class="px-4 py-3 text-foreground/90 font-medium whitespace-nowrap">
                                {{ formatCell(row[col.fieldname], col.fieldtype) }}
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</template>
