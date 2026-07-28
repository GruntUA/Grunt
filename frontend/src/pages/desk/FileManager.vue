<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { UploadCloud, File as FileIcon, Trash2, Search, Download, Folder } from '@lucide/vue'
import { filesApi, type FileItem } from '@/core/api/files'

const files = ref<FileItem[]>([])
const loading = ref(false)
const uploading = ref(false)
const searchQuery = ref('')
const isDragging = ref(false)

async function loadFiles() {
    loading.value = true
    try {
        const res = await filesApi.list({ search: searchQuery.value })
        files.value = res.items
    } finally {
        loading.value = false
    }
}

async function handleFileSelect(event: Event) {
    const target = event.target as HTMLInputElement
    if (target.files && target.files.length > 0) {
        await uploadFile(target.files[0])
        target.value = '' // Reset input
    }
}

async function handleDrop(event: DragEvent) {
    isDragging.value = false
    if (event.dataTransfer?.files && event.dataTransfer.files.length > 0) {
        await uploadFile(event.dataTransfer.files[0])
    }
}

async function uploadFile(file: File) {
    uploading.value = true
    try {
        const uploaded = await filesApi.upload(file)
        files.value.unshift(uploaded)
    } catch (error) {
        console.error('Failed to upload file', error)
    } finally {
        uploading.value = false
    }
}

async function removeFile(id: string) {
    if (!confirm('Видалити файл?')) return
    await filesApi.delete(id)
    files.value = files.value.filter(f => f.id !== id)
}

function formatBytes(bytes: number, decimals = 2) {
    if (!+bytes) return '0 Bytes'
    const k = 1024
    const dm = decimals < 0 ? 0 : decimals
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`
}

function isImage(contentType: string) {
    return contentType.startsWith('image/')
}

const displayFiles = computed(() => files.value)

onMounted(loadFiles)

let searchTimeout: number
function onSearchInput() {
    window.clearTimeout(searchTimeout)
    searchTimeout = window.setTimeout(loadFiles, 300)
}
</script>

<template>
    <div class="flex flex-col h-[calc(100vh-64px)] px-8 -mx-8 bg-muted/10">
        <div class="py-6 flex flex-col md:flex-row items-center justify-between gap-4 shrink-0">
            <div class="flex items-center gap-3">
                <div
                    class="size-10 rounded-xl bg-primary/10 flex items-center justify-center border border-primary/20 shadow-inner">
                    <Folder class="size-5 text-primary" />
                </div>
                <div>
                    <h1 class="text-xl font-bold text-foreground">Менеджер файлів</h1>
                    <p class="text-sm text-muted-foreground">Завантажуйте та керуйте документами і медіа</p>
                </div>
            </div>
            <div class="flex items-center gap-3 w-full md:w-auto md:flex-1 md:justify-end">
                <div class="relative w-full md:max-w-xs xl:max-w-md">
                    <Search class="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
                    <Input v-model="searchQuery" placeholder="Введіть назву файла..." class="pl-9 h-9 w-full"
                        @input="onSearchInput" />
                </div>
                <div class="relative overflow-hidden group shrink-0">
                    <Button :disabled="uploading" class="h-9 whitespace-nowrap px-4">
                        <Spinner v-if="uploading" class="size-4! mr-2" strokeWidth="8" />
                        <UploadCloud v-else class="size-4 mr-2" />
                        Завантажити
                    </Button>
                    <input type="file" class="absolute inset-0 opacity-0 cursor-pointer" @change="handleFileSelect"
                        :disabled="uploading" />
                </div>
            </div>
        </div>

        <!-- Dropzone and Grid Context -->
        <div class="flex-1 flex flex-col overflow-y-auto rounded-3xl border-2 border-dashed bg-card transition-all mb-8 relative p-6 custom-scrollbar min-h-[400px]"
            :class="isDragging ? 'border-primary bg-primary/5 shadow-inner' : 'border-border shadow-sm'"
            @dragover.prevent="isDragging = true" @dragleave.prevent="isDragging = false" @drop.prevent="handleDrop">
            <div v-if="isDragging"
                class="absolute inset-0 z-10 flex items-center justify-center backdrop-blur-sm bg-background/50 rounded-3xl pointer-events-none">
                <div
                    class="flex flex-col items-center bg-card p-6 rounded-2xl shadow-xl border border-primary/20 animate-in zoom-in duration-200">
                    <UploadCloud class="size-12 text-primary mb-2" />
                    <h3 class="text-lg font-bold text-primary">Відпустіть файл тут</h3>
                </div>
            </div>

            <div v-if="loading" class="flex-1 flex items-center justify-center">
                <Spinner class="size-10!" />
            </div>

            <div v-else-if="files.length === 0"
                class="flex-1 flex flex-col items-center justify-center text-center pb-20 p-4">
                <div class="size-20 rounded-full bg-primary/5 flex items-center justify-center mb-6">
                    <UploadCloud class="size-10 text-primary/40" />
                </div>
                <h3 class="text-2xl font-bold mb-3">Немає файлів</h3>
                <p class="text-muted-foreground max-w-md md:max-w-xl mb-6 text-sm md:text-base px-4">
                    Перетягніть сюди файли або скористайтеся кнопкою «Завантажити» у правому верхньому куті.
                </p>
            </div>

            <div v-else class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4 pb-8">
                <div v-for="file in displayFiles" :key="file.id"
                    class="group relative aspect-square rounded-2xl border bg-background shadow-xs hover:shadow-md hover:border-primary/30 transition-all flex flex-col overflow-hidden">
                    <!-- Preview Area -->
                    <div class="flex-1 flex flex-col relative w-full items-center justify-center bg-muted/20 border-b">
                        <!-- Image Preview -->
                        <img v-if="isImage(file.content_type)" :src="file.url"
                            class="absolute inset-0 w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                            loading="lazy" />
                        <!-- Document Preview Placeholder -->
                        <div v-else
                            class="flex flex-col items-center justify-center group-hover:scale-110 transition-transform duration-500">
                            <FileIcon class="size-10 text-muted-foreground/30 mb-2" />
                        </div>

                        <!-- Absolute overlay actions -->
                        <div
                            class="absolute inset-x-0 top-0 p-2 bg-gradient-to-b from-black/60 to-transparent flex items-start justify-end opacity-0 group-hover:opacity-100 transition-opacity">
                            <button @click="removeFile(file.id)"
                                class="size-7 rounded-full bg-background/20 hover:bg-destructive text-white backdrop-blur-md flex items-center justify-center transition-colors"
                                title="Видалити">
                                <Trash2 class="size-3.5" />
                            </button>
                        </div>
                        <!-- Center action -->
                        <div
                            class="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
                            <a :href="file.url" download target="_blank"
                                class="size-10 rounded-full bg-background/80 hover:bg-primary text-foreground hover:text-primary-foreground backdrop-blur-md flex items-center justify-center transition-colors pointer-events-auto border border-white/20 shadow-lg"
                                title="Завантажити">
                                <Download class="size-4" />
                            </a>
                        </div>
                    </div>

                    <!-- Metadata Area -->
                    <div class="p-3 shrink-0 flex flex-col bg-background/95 backdrop-blur-md">
                        <p class="text-xs font-bold truncate text-foreground/90 mb-1" :title="file.filename">{{
                            file.filename }}</p>
                        <div
                            class="flex items-center justify-between text-[10px] uppercase font-bold text-muted-foreground">
                            <Badge variant="secondary"
                                class="text-[9px] px-1 bg-muted/30 border-transparent truncate max-w-[60px]">
                                {{ file.content_type.split('/')[1] || 'FILE' }}
                            </Badge>
                            <span class="tabular-nums opacity-70">{{ formatBytes(file.size_bytes) }}</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
    height: 8px;
    width: 6px;
}

.custom-scrollbar::-webkit-scrollbar-track {
    background: transparent;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
    background: rgba(0, 0, 0, 0.1);
    border-radius: 10px;
}

.custom-scrollbar:hover::-webkit-scrollbar-thumb {
    background: rgba(var(--primary), 0.3);
}
</style>
