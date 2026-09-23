<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { UploadCloud, File as FileIcon, Trash2, Search, Download, Folder, AlertCircle, Layers } from '@lucide/vue'
import { filesApi, type FileItem } from '@/core/api/files'
import { useFileList, type FileCategory } from '@/core/composables/useFileList'
import { useDebounce } from '@/core/composables/useDebounce'
import { useToast } from '@/core/composables/useToast'
import { fileTypeLabel, formatFileSize, previewUrl } from '@/core/fileUtils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { Skeleton } from '@/components/ui/skeleton'

const searchQuery = ref('')
const debouncedSearch = useDebounce(searchQuery, 300)
const category = ref<FileCategory>('all')
const sort = ref<'new' | 'name' | 'size'>('new')
const uploading = ref(false)
const isDragging = ref(false)
const deletingId = ref<string | null>(null)
const deduping = ref(false)
const toast = useToast()

const categoryTabs: { id: FileCategory; label: string }[] = [
  { id: 'all', label: 'Усі' },
  { id: 'image', label: 'Зображення' },
  { id: 'pdf', label: 'PDF' },
  { id: 'document', label: 'Документи' },
]

const {
  items,
  total,
  isLoading,
  isError,
  isFetchingNextPage,
  hasNextPage,
  fetchNextPage,
  refetch,
} = useFileList({
  search: debouncedSearch,
  category: () => category.value,
  orderBy: () => (sort.value === 'name' ? 'file_name' : sort.value === 'size' ? 'file_size' : 'created_at'),
  order: () => (sort.value === 'name' ? 'asc' : 'desc'),
  pageSize: 40,
})

// Infinite scroll
const sentinel = ref<HTMLDivElement>()
const scrollEl = ref<HTMLDivElement>()
let observer: IntersectionObserver | null = null

onMounted(() => {
  observer = new IntersectionObserver(
    entries => {
      if (entries[0].isIntersecting && hasNextPage.value && !isFetchingNextPage.value) fetchNextPage()
    },
    { root: scrollEl.value ?? null, threshold: 0.1 },
  )
  if (sentinel.value) observer.observe(sentinel.value)
})
onUnmounted(() => observer?.disconnect())

async function handleFileSelect(event: Event) {
  const target = event.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    await uploadFile(target.files[0])
    target.value = ''
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
    await filesApi.upload(file)
    await refetch()
  } catch (error) {
    console.error('Failed to upload file', error)
  } finally {
    uploading.value = false
  }
}

async function removeFile(item: FileItem) {
  if (!confirm('Видалити файл?')) return
  deletingId.value = item.id
  try {
    await filesApi.delete(item.id)
    await refetch()
  } finally {
    deletingId.value = null
  }
}

async function dedupeStorage() {
  if (!confirm('Об’єднати однакові файли на диску? Записи та посилання не змінюються.')) return
  deduping.value = true
  try {
    const r = await filesApi.dedupeStorage()
    await refetch()
    if (r.freed_blobs) {
      toast.success(
        `Звільнено ${formatFileSize(r.freed_bytes)} (${r.freed_blobs} копій, груп: ${r.duplicate_groups})`,
      )
    } else {
      toast.info('Дублікатів не знайдено')
    }
  } catch {
    toast.error('Не вдалося обробити дублікати')
  } finally {
    deduping.value = false
  }
}

watch([category, sort], () => scrollEl.value?.scrollTo({ top: 0 }))
</script>

<template>
    <div class="flex flex-col h-[calc(100vh-64px)] px-8 -mx-8 bg-muted/10">
        <div class="py-6 flex flex-col md:flex-row items-center justify-between gap-4 shrink-0">
            <div class="flex items-center gap-3">
                <div
                    class="size-10 rounded-lg bg-primary/10 flex items-center justify-center border border-primary/20 shadow-inner">
                    <Folder class="size-5 text-primary" />
                </div>
                <div>
                    <h1 class="text-xl font-semibold text-foreground">Менеджер файлів</h1>
                    <p class="text-muted-foreground">
                        Завантажуйте та керуйте документами і медіа<span v-if="total"> · {{ total }}</span>
                    </p>
                </div>
            </div>
            <div class="flex items-center gap-3 w-full md:w-auto md:flex-1 md:justify-end">
                <div class="relative w-full md:max-w-xs xl:max-w-md">
                    <Search class="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
                    <Input v-model="searchQuery" placeholder="Введіть назву файла..." class="pl-9 h-9 w-full" />
                </div>
                <Button variant="outline" :disabled="deduping" class="h-9 whitespace-nowrap px-4"
                    title="Об’єднати однакові файли на диску" @click="dedupeStorage">
                    <Spinner v-if="deduping" class="size-4! mr-2" strokeWidth="8" />
                    <Layers v-else class="size-4 mr-2" />
                    Дублікати
                </Button>
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

        <!-- Filter bar -->
        <div class="flex items-center gap-2 pb-3 shrink-0">
            <div class="flex gap-1">
                <button
                    v-for="tab in categoryTabs"
                    :key="tab.id"
                    type="button"
                    class="rounded px-2.5 py-1 text-sm transition-colors"
                    :class="category === tab.id ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:bg-muted'"
                    @click="category = tab.id"
                >
                    {{ tab.label }}
                </button>
            </div>
            <select v-model="sort"
                class="ml-auto h-8 rounded-md border border-input bg-transparent px-2 text-sm outline-none">
                <option value="new">Спочатку нові</option>
                <option value="name">За назвою</option>
                <option value="size">За розміром</option>
            </select>
        </div>

        <!-- Dropzone and Grid Context -->
        <div ref="scrollEl" class="flex-1 flex flex-col overflow-y-auto rounded-lg border-2 border-dashed bg-card transition-all mb-8 relative p-6 custom-scrollbar min-h-[400px]"
            :class="isDragging ? 'border-primary bg-primary/5 shadow-inner' : 'border-border shadow-sm'"
            @dragover.prevent="isDragging = true" @dragleave.prevent="isDragging = false" @drop.prevent="handleDrop">
            <div v-if="isDragging"
                class="absolute inset-0 z-10 flex items-center justify-center bg-background/50 rounded-lg pointer-events-none">
                <div
                    class="flex flex-col items-center bg-card p-6 rounded-lg shadow-md border border-primary/20 animate-in zoom-in duration-200">
                    <UploadCloud class="size-12 text-primary mb-2" />
                    <h3 class="text-lg font-semibold text-primary">Відпустіть файл тут</h3>
                </div>
            </div>

            <div v-if="isLoading"
                class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
                <Skeleton v-for="i in 12" :key="i" class="aspect-square w-full rounded-lg" />
            </div>

            <div v-else-if="isError" class="flex-1 flex flex-col items-center justify-center gap-3 text-center">
                <AlertCircle class="size-10 text-muted-foreground/40" />
                <h3 class="text-lg font-semibold">Не вдалося завантажити файли</h3>
                <button class="text-sm text-primary hover:underline" @click="refetch()">Спробувати ще</button>
            </div>

            <div v-else-if="items.length === 0"
                class="flex-1 flex flex-col items-center justify-center text-center pb-20 p-4">
                <div class="size-20 rounded-full bg-primary/5 flex items-center justify-center mb-6">
                    <UploadCloud class="size-10 text-primary/40" />
                </div>
                <h3 class="text-2xl font-semibold mb-3">Немає файлів</h3>
                <p class="text-muted-foreground max-w-md md:max-w-xl mb-6 md:text-base px-4">
                    Перетягніть сюди файли або скористайтеся кнопкою «Завантажити» у правому верхньому куті.
                </p>
            </div>

            <div v-else class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4 pb-8">
                <div v-for="file in items" :key="file.id"
                    class="group relative aspect-square rounded-lg border bg-background shadow-xs hover:shadow-md hover:border-primary/30 transition-all flex flex-col overflow-hidden">
                    <!-- Preview Area -->
                    <div class="flex-1 flex flex-col relative w-full items-center justify-center bg-muted/20 border-b">
                        <img v-if="previewUrl(file)" :src="previewUrl(file)!"
                            class="absolute inset-0 w-full h-full object-cover object-top group-hover:scale-105 transition-transform duration-500"
                            loading="lazy" />
                        <div v-else class="flex flex-col items-center justify-center">
                            <FileIcon class="size-10 text-muted-foreground/30 mb-2" />
                        </div>

                        <div
                            class="absolute inset-x-0 top-0 p-2 bg-black/40 flex items-start justify-end opacity-0 group-hover:opacity-100 transition-opacity">
                            <button @click="removeFile(file)"
                                class="size-7 rounded-full bg-background/20 hover:bg-destructive text-white flex items-center justify-center transition-colors"
                                title="Видалити">
                                <Spinner v-if="deletingId === file.id" class="size-3.5!" />
                                <Trash2 v-else class="size-3.5" />
                            </button>
                        </div>
                        <div
                            class="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
                            <a :href="file.url" download target="_blank"
                                class="size-10 rounded-full bg-background/80 hover:bg-primary text-foreground hover:text-primary-foreground flex items-center justify-center transition-colors pointer-events-auto border border-white/20 shadow-md"
                                title="Завантажити">
                                <Download class="size-4" />
                            </a>
                        </div>
                    </div>

                    <div class="p-3 shrink-0 flex flex-col bg-background/95">
                        <p class="font-semibold truncate text-foreground/90 mb-1" :title="file.filename">{{
                            file.filename }}</p>
                        <div class="flex items-center justify-between uppercase font-semibold text-muted-foreground">
                            <Badge variant="secondary"
                                class="text-xs px-1 bg-muted/30 border-transparent truncate max-w-[60px]">
                                {{ fileTypeLabel(file.filename, file.content_type) }}
                            </Badge>
                            <span class="tabular-nums opacity-70">{{ formatFileSize(file.size_bytes) }}</span>
                        </div>
                    </div>
                </div>
            </div>

            <div ref="sentinel" class="h-8 mt-2 flex justify-center shrink-0">
                <Spinner v-if="isFetchingNextPage" class="size-5!" />
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
    background: var(--border);
    border-radius: 10px;
}

.custom-scrollbar:hover::-webkit-scrollbar-thumb {
    background: color-mix(in srgb, var(--primary) 30%, transparent);
}
</style>
