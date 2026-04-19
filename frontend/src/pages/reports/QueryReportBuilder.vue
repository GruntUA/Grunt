<script setup lang="ts">
import { ref, watch, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import api from '@/core/api/client'
import { metaApi } from '@/core/api/meta'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import Select from 'primevue/select'
import { Badge } from '@/components/ui/badge'
import {
    Plus, Search, Save, Play, Trash2, ChevronRight,
    Layout, Table as TableIcon, FileBarChart
} from '@lucide/vue'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger, TabsContent, TabPanels } from '@/components/ui/tabs'

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
const reportTitle = ref(props.reportName || 'Новий звіт')

const columns = ref<any[]>([]) // { fieldname, label, aggregation, fieldtype }
const previewData = ref<any[]>([])
const previewCols = ref<any[]>([])
const previewMeta = ref<any>(null)

const AGGREGATIONS = [
    { value: 'none', label: 'Немає' },
    { value: 'sum', label: 'Сума (SUM)' },
    { value: 'count', label: 'Кількість (COUNT)' },
    { value: 'avg', label: 'Середнє (AVG)' },
    { value: 'min', label: 'Мінімум (MIN)' },
    { value: 'max', label: 'Максимум (MAX)' },
]

onMounted(async () => {
    const res = await api.get('/api/v1/meta/doctypes')
    doctypes.value = res.data

    // Auto-select from query
    if (route.query.doctype) {
        selectedDoctype.value = route.query.doctype as string
    }

    if (props.reportName && props.reportName !== 'new') {
        const repRes = await api.get(`/api/v1/reports/${props.reportName}`)
        const rep = repRes.data.data
        selectedDoctype.value = rep.doctype
        columns.value = JSON.parse(rep.columns || '[]')
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

async function runPreview() {
    if (!selectedDoctype.value || columns.value.length === 0) return

    previewLoading.value = true
    try {
        const res = await api.post('/api/v1/reports/run-preview', {
            doctype: selectedDoctype.value,
            columns: columns.value,
            filters: {}
        })
        previewData.value = res.data.data
        previewCols.value = res.data.columns
        previewMeta.value = res.data.meta
    } finally {
        previewLoading.value = false
    }
}

async function saveReport() {
    if (!reportTitle.value || !selectedDoctype.value) {
        alert('Вкажіть назву та тип документа')
        return
    }

    loading.value = true
    try {
        const payload = {
            report_name: reportTitle.value,
            doctype: selectedDoctype.value,
            report_type: 'List',
            columns: JSON.stringify(columns.value),
            filters_config: '{}'
        }

        if (props.reportName && props.reportName !== 'new') {
            await api.put(`/api/v1/reports/${props.reportName}`, payload)
        } else {
            await api.post('/api/v1/reports/', payload)
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
                <div class="flex items-center gap-2">
                    <FileBarChart class="size-5 text-primary" />
                    <Input v-model="reportTitle" placeholder="Назва звіту"
                        class="font-bold border-none focus-visible:ring-0 px-0 h-8 text-lg" />
                </div>

                <div class="space-y-2">
                    <label class="text-[11px] font-bold uppercase tracking-widest text-muted-foreground">Тип
                        документа</label>
                    <Select
                        v-model="selectedDoctype"
                        :options="doctypes"
                        option-label="label"
                        option-value="name"
                        placeholder="Оберіть DocType"
                        class="w-full"
                    />
                </div>
            </div>

            <!-- Fields & Columns Tabs -->
            <Tabs default-value="columns" class="flex-1 flex flex-col overflow-hidden">
                <TabsList variant="underline" class="w-full justify-start h-auto overflow-x-auto scrollbar-none">
                    <TabsTrigger value="columns" variant="underline" class="flex-1">Колонки</TabsTrigger>
                    <!-- <TabsTrigger value="filters" variant="underline" class="flex-1 opacity-50">Фільтри</TabsTrigger> -->
                </TabsList>

                <TabPanels>
                <TabsContent value="columns" class="flex-1 overflow-y-auto p-4 space-y-6 focus-visible:ring-0 m-0">
                    <!-- Selected Columns -->
                    <div class="space-y-3">
                        <div class="flex items-center justify-between">
                            <h4 class="text-xs font-bold uppercase text-muted-foreground flex items-center gap-1.5">
                                <TableIcon class="size-3.5" />
                                Вибрані стовпці ({{ columns.length }})
                            </h4>
                        </div>

                        <div v-if="columns.length === 0"
                            class="border-2 border-dashed rounded-xl p-8 text-center text-xs text-muted-foreground bg-muted/20">
                            Додайте поля зі списку нижче
                        </div>

                        <div v-for="(col, index) in columns" :key="col.fieldname"
                            class="group flex flex-col gap-2 p-3 rounded-lg border bg-background hover:border-primary/30 transition-all shadow-sm">
                            <div class="flex items-center justify-between">
                                <div class="flex items-center gap-2 min-w-0">
                                    <Badge variant="outline"
                                        class="h-5 px-1.5 text-[9px] font-bold uppercase opacity-50 shrink-0">{{
                                            col.fieldtype }}</Badge>
                                    <span class="text-sm font-semibold truncate">{{ col.label }}</span>
                                </div>
                                <button @click="removeColumn(index)"
                                    class="opacity-0 group-hover:opacity-100 p-1 text-muted-foreground hover:text-destructive transition-all">
                                    <Trash2 class="size-4" />
                                </button>
                            </div>

                            <div class="flex items-center gap-2">
                                <Select
                                    v-model="col.aggregation"
                                    :options="AGGREGATIONS"
                                    option-label="label"
                                    option-value="value"
                                    placeholder="Агрегація"
                                    class="h-7 text-[11px]"
                                />
                            </div>
                        </div>
                    </div>

                    <!-- Available Fields -->
                    <div v-if="selectedDoctype" class="space-y-3">
                        <h4 class="text-xs font-bold uppercase text-muted-foreground flex items-center gap-1.5">
                            <Plus class="size-3.5" />
                            Доступні поля
                        </h4>
                        <div class="relative">
                            <Search class="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground" />
                            <Input v-model="filteredFields" placeholder="Пошук полів..."
                                class="h-9 pl-8 text-xs bg-muted/20 border-none" />
                        </div>
                        <div class="grid grid-cols-1 gap-1">
                            <button v-for="f in displayFields" :key="f.fieldname"
                                class="flex items-center justify-between px-3 py-2 rounded-lg text-left text-sm hover:bg-muted text-foreground/80 group transition-colors"
                                @click="addColumn(f)" :disabled="columns.some(c => c.fieldname === f.fieldname)"
                                :class="{ 'opacity-50 cursor-not-allowed': columns.some(c => c.fieldname === f.fieldname) }">
                                <div class="flex flex-col min-w-0">
                                    <span class="font-medium truncate">{{ f.label }}</span>
                                    <span class="text-[10px] text-muted-foreground">{{ f.fieldname }}</span>
                                </div>
                                <Plus class="size-4 opacity-0 group-hover:opacity-100 text-primary transition-all" />
                            </button>
                        </div>
                    </div>
                </TabsContent>
                </TabPanels>
            </Tabs>

            <!-- Sidebar Footer -->
            <div class="p-4 border-t flex flex-col gap-2 bg-muted/10">
                <Button :disabled="previewLoading || !selectedDoctype || columns.length === 0" @click="runPreview"
                    variant="secondary" class="w-full h-10 font-bold">
                    <Play class="size-4 mr-2" :class="{ 'animate-pulse': previewLoading }" />
                    Переглянути
                </Button>
                <div class="flex gap-2">
                    <Button :disabled="loading || columns.length === 0" @click="saveReport"
                        class="flex-1 h-10 font-bold">
                        <Save class="size-4 mr-2" />
                        Зберегти
                    </Button>
                    <Button variant="outline" class="h-10 px-3" @click="router.back()">Скасувати</Button>
                </div>
            </div>
        </aside>

        <!-- Main: Preview -->
        <main class="flex-1 flex flex-col bg-muted/10 overflow-hidden">
            <!-- Tools -->
            <header class="p-8 pb-4 flex justify-between items-center">
                <div class="flex items-center gap-2 text-sm text-muted-foreground/80 font-medium">
                    <span>Звіти</span>
                    <ChevronRight class="size-3 opacity-50" />
                    <span class="text-foreground font-bold">{{ reportTitle }}</span>
                </div>
            </header>

            <div class="flex-1 px-8 pb-8 overflow-hidden flex flex-col">
                <div v-if="previewCols.length === 0 && !previewLoading"
                    class="flex-1 flex flex-col items-center justify-center p-12 text-center rounded-3xl border-2 border-dashed bg-card/30">
                    <div class="size-16 rounded-full bg-primary/5 flex items-center justify-center mb-4">
                        <Layout class="size-8 text-primary/40" />
                    </div>
                    <h3 class="text-xl font-bold mb-2">Налаштуйте звіт</h3>
                    <p class="text-muted-foreground max-w-sm mb-6">Оберіть DocType та додайте стовпці у боковій панелі,
                        щоб побачити результат.</p>
                    <Button variant="outline" @click="selectedDoctype = doctypes[0]?.name"
                        v-if="!selectedDoctype">Обрати перший доступний DocType</Button>
                </div>

                <div v-else class="flex-1 bg-card rounded-2xl border shadow-xl overflow-hidden flex flex-col">
                    <!-- Table Toolbar -->
                    <div class="p-4 border-b flex items-center justify-between bg-muted/20">
                        <div
                            class="flex items-center gap-4 text-xs font-bold text-muted-foreground uppercase tracking-widest">
                            <span class="flex items-center gap-1.5">
                                <TableIcon class="size-3.5" /> Результат
                            </span>
                            <span v-if="previewMeta">{{ previewMeta.rows }} рядків</span>
                            <span v-if="previewMeta">{{ previewMeta.time_ms }}мс</span>
                        </div>
                        <div v-if="previewLoading" class="flex items-center gap-2">
                            <div class="size-2 rounded-full bg-primary animate-ping" />
                            <span
                                class="text-[10px] font-bold text-primary italic uppercase anima">Завантаження...</span>
                        </div>
                    </div>

                    <!-- Results Table -->
                    <div class="flex-1 overflow-auto">
                        <table class="w-full text-sm">
                            <thead class="sticky top-0 bg-background/95 backdrop-blur-md z-10">
                                <tr class="border-b shadow-sm">
                                    <th v-for="col in previewCols" :key="col.fieldname"
                                        class="px-4 py-3 text-left font-bold text-muted-foreground uppercase tracking-wider text-[11px] whitespace-nowrap">
                                        {{ col.label }}
                                    </th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr v-if="previewLoading && previewData.length === 0" v-for="i in 10" :key="i"
                                    class="border-b last:border-0 opacity-50">
                                    <td v-for="col in previewCols.length || 5" :key="col" class="px-4 py-4">
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
/* Glassy effect for selected rows */
tr.bg-primary\/5 {
    background: linear-gradient(to right, rgba(var(--primary), 0.08), rgba(var(--primary), 0.03));
}

/* Hide scrollbar but keep functionality */
.scrollbar-none::-webkit-scrollbar {
  display: none;
}
.scrollbar-none {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
</style>
