<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/core/api/client'
import { filesApi } from '@/core/api/files'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

const props = defineProps<{
    workspaceName: string
    id?: string
}>()

const router = useRouter()

const currentStep = ref(1)
const loading = ref(false)
const doctypes = ref<any[]>([])
const selectedDoctype = ref('')
const file = ref<File | null>(null)
const importId = ref(props.id || '')
const fileInput = ref<HTMLInputElement | null>(null)

const mapping = ref<Record<string, string>>({})
const previewData = ref<any>(null)
const importStatus = ref<any>(null)

// Step 1: Init
onMounted(async () => {
    const res = await api.get('/api/v1/meta/doctypes')
    doctypes.value = res.data

    if (importId.value) {
        await loadImport(importId.value)
    }
})

async function loadImport(id: string) {
    loading.value = true
    try {
        const res = await api.get(`/api/v1/docs/DataImport/${id}`)
        const doc = res.data
        selectedDoctype.value = doc.doctype_name
        importId.value = doc.id

        // If pending, move to mapping
        if (doc.status === 'Pending') {
            await getPreview()
            currentStep.value = 2
        } else {
            importStatus.value = doc
            currentStep.value = 3
        }
    } finally {
        loading.value = false
    }
}

async function handleFileUpload(event: any) {
    file.value = event.target.files[0]
}

async function startImport() {
    if (!selectedDoctype.value || !file.value) return

    loading.value = true
    const formData = new FormData()
    formData.append('file', file.value)

    try {
        // 1. Upload file using whitelisted method
        const fileData = await filesApi.upload(file.value)

        // 2. Create DataImport doc
        const diRes = await api.post('/api/v1/docs/DataImport', {
            doctype_name: selectedDoctype.value,
            file: fileData.url,
            status: 'Pending',
            import_type: 'Insert New'
        })

        importId.value = diRes.data.id
        router.push({ name: 'data-import', params: { workspaceName: props.workspaceName, id: importId.value } })
        await getPreview()
        currentStep.value = 2
    } catch (err: any) {
        alert('Помилка: ' + (err.response?.data?.error?.message || err.message))
    } finally {
        loading.value = false
    }
}

async function getPreview() {
    loading.value = true
    try {
        const res = await api.get(`/api/v1/data-import/preview/${importId.value}`)
        previewData.value = res.data
        mapping.value = res.data.suggested_mapping
    } finally {
        loading.value = false
    }
}

async function runImport() {
    loading.value = true
    try {
        // Save mapping first
        await api.patch(`/api/v1/docs/DataImport/${importId.value}`, {
            mapping: JSON.stringify(mapping.value),
            status: 'In Progress'
        })

        await api.post(`/api/v1/data-import/run/${importId.value}`)
        currentStep.value = 3
        pollStatus()
    } finally {
        loading.value = false
    }
}

async function pollStatus() {
    const interval = setInterval(async () => {
        const res = await api.get(`/api/v1/docs/DataImport/${importId.value}`)
        importStatus.value = res.data
        if (['Success', 'Failed', 'Partial Success'].includes(res.data.status)) {
            clearInterval(interval)
        }
    }, 2000)
}
</script>

<template>
    <div class="p-6 max-w-4xl mx-auto">
        <div class="mb-8">
            <h1 class="text-2xl font-bold mb-2">Імпорт даних</h1>
            <div class="flex gap-4">
                <div class="flex items-center gap-2"
                    :class="currentStep >= 1 ? 'text-primary' : 'text-muted-foreground'">
                    <Badge severity="contrast" :class="currentStep === 1 ? 'bg-primary text-white' : ''">1</Badge> Вибір
                    файлу
                </div>
                <div class="flex items-center gap-2"
                    :class="currentStep >= 2 ? 'text-primary' : 'text-muted-foreground'">
                    <Badge severity="contrast" :class="currentStep === 2 ? 'bg-primary text-white' : ''">2</Badge> Мапінг
                    полів
                </div>
                <div class="flex items-center gap-2"
                    :class="currentStep >= 3 ? 'text-primary' : 'text-muted-foreground'">
                    <Badge severity="contrast" :class="currentStep === 3 ? 'bg-primary text-white' : ''">3</Badge>
                    Виконання
                </div>
            </div>
        </div>

        <!-- Step 1 -->
        <div v-if="currentStep === 1" class="space-y-6 bg-card p-8 border rounded-xl shadow-sm">
            <div class="space-y-2">
                <label class="font-medium">Оберіть тип документа для імпорту</label>
                <select v-model="selectedDoctype" class="w-full p-2 border rounded-md bg-background text-foreground">
                    <option value="">Оберіть DocType...</option>
                    <option v-for="dt in doctypes" :key="dt.name" :value="dt.name">{{ dt.label || dt.name }}</option>
                </select>
            </div>

            <div class="space-y-2">
                <label class="font-medium">Завантажте файл (CSV або XLSX)</label>
                <div class="border-2 border-dashed rounded-xl p-12 text-center hover:bg-muted transition-colors cursor-pointer"
                    @click="fileInput?.click()">
                    <input type="file" ref="fileInput" class="hidden" @change="handleFileUpload" accept=".csv,.xlsx">
                    <div v-if="!file" class="text-muted-foreground">Натисніть або перетягніть файл сюди</div>
                    <div v-else class="font-medium text-primary">{{ file.name }}</div>
                </div>
            </div>

            <div class="flex justify-end">
                <Button @click="startImport" :disabled="!selectedDoctype || !file || loading">
                    {{ loading ? 'Завантаження...' : 'Продовжити' }}
                </Button>
            </div>
        </div>

        <!-- Step 2 -->
        <div v-if="currentStep === 2 && previewData" class="space-y-6">
            <div class="bg-card border rounded-xl overflow-hidden">
                <table class="w-full text-sm">
                    <thead class="bg-muted border-b">
                        <tr>
                            <th class="p-3 text-left">Колонка файлу</th>
                            <th class="p-3 text-left">Поле системи</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr v-for="header in previewData.headers" :key="header" class="border-b">
                            <td class="p-3 font-medium">{{ header }}</td>
                            <td class="p-3">
                                <select v-model="mapping[header]" class="p-1 border rounded w-full">
                                    <option value="">Не імпортувати</option>
                                    <option v-for="f in previewData.doctype_fields" :key="f.fieldname"
                                        :value="f.fieldname">{{ f.label }}</option>
                                </select>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <div class="flex justify-between">
                <Button variant="outline" @click="currentStep = 1">Назад</Button>
                <Button @click="runImport" :disabled="loading">Почати імпорт</Button>
            </div>
        </div>

        <!-- Step 3 -->
        <div v-if="currentStep === 3" class="space-y-6 bg-card p-8 border rounded-xl">
            <div v-if="importStatus" class="space-y-6">
                <div class="text-center">
                    <div class="text-lg font-bold mb-2">{{ importStatus.status }}</div>
                    <div class="text-sm text-muted-foreground">Оброблено {{ importStatus.processed_rows }} з {{
                        importStatus.total_rows }} рядків</div>
                </div>

                <div class="w-full bg-muted rounded-full h-2 overflow-hidden">
                    <div class="bg-primary h-full transition-all duration-500"
                        :style="{ width: `${(importStatus.processed_rows / importStatus.total_rows) * 100}%` }"></div>
                </div>

                <div v-if="importStatus.error_count > 0" class="p-4 bg-destructive/10 text-destructive rounded-lg text-sm">
                    <div class="font-bold mb-2 text-base">Знайдено {{ importStatus.error_count }} помилок:</div>
                    <ul class="list-disc pl-5">
                        <li v-for="err in JSON.parse(importStatus.error_log)" :key="err.row">
                            Рядок {{ err.row }}: {{ err.error }}
                        </li>
                    </ul>
                </div>

                <div class="flex justify-center">
                    <Button @click="router.push(`/${workspaceName}`)">На головну</Button>
                </div>
            </div>
            <div v-else class="text-center p-12">
                Підготовка імпорту...
            </div>
        </div>
    </div>
</template>
