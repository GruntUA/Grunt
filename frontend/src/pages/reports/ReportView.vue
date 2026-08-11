<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/core/api/client'
import { useAuthStore } from '@/stores/auth'
import { Download, RefreshCw, Settings2, FileBarChart2, FileX } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

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

async function fetchReport() {
    loading.value = true
    try {
        // 1. Fetch metadata
        const metaRes = await api.get(`/api/v1/reports/${props.reportName}`)
        report.value = metaRes.data.data
        
        // 2. Run report
        const runRes = await api.post(`/api/v1/reports/${props.reportName}/run`, {
            filters: filters.value
        })
        data.value = runRes.data.data
        columns.value = runRes.data.columns
        meta.value = runRes.data.meta
    } finally {
        loading.value = false
    }
}

onMounted(fetchReport)
watch(() => props.reportName, fetchReport)

function formatCell(val: any, fieldtype: string): string {
    if (val === null || val === undefined || val === '') return '—'
    if (fieldtype === 'Date') return new Date(val).toLocaleDateString('uk-UA')
    if (fieldtype === 'Datetime') return new Date(val).toLocaleString('uk-UA')
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
                    <p class="text-muted-foreground text-sm" v-if="meta">
                        {{ meta.rows }} записів • {{ meta.time_ms }}мс
                    </p>
                </div>
            </div>
            
            <div class="flex items-center gap-2">
                <Button variant="outline" size="sm" @click="fetchReport" :disabled="loading">
                    <RefreshCw class="size-4 mr-2" :class="{ 'animate-spin': loading }" />
                    Оновити
                </Button>
                <Button variant="outline" size="sm" as="a" :href="`/api/v1/reports/${reportName}/export/xlsx?token=${auth.token}`" download>
                    <Download class="size-4 mr-2" />
                    XLSX
                </Button>
                <Button size="sm" @click="openBuilder" v-if="auth.user?.is_superadmin">
                    <Settings2 class="size-4 mr-2" />
                    Конструктор
                </Button>
            </div>
        </div>

        <!-- Filters (Placeholder) -->
        <div v-if="report?.filters_config" class="p-4 rounded-lg border bg-card/50">
            <!-- Filter logic here -->
            <p class="text-xs text-muted-foreground uppercase font-semibold tracking-wider">Фільтри</p>
            <div class="mt-2 text-sm text-muted-foreground italic">Конфігурація фільтрів ще не реалізована</div>
        </div>

        <!-- Table -->
        <div class="border rounded-lg overflow-hidden shadow-sm bg-card">
            <div class="overflow-x-auto">
                <table class="w-full text-sm">
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
