<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import type { AttachmentResult } from '@/core/attachmentChannels/types'
import { filesApi, type FileItem } from '@/core/api/files'
import { useDebounce } from '@/core/composables/useDebounce'
import { File as FileIcon } from '@lucide/vue'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'

const props = defineProps<{ imageOnly: boolean }>()
const emit = defineEmits<{ select: [result: AttachmentResult] }>()

const search = ref('')
const debouncedSearch = useDebounce(search, 300)
const items = ref<FileItem[]>([])
const page = ref(1)
const hasMore = ref(true)
const isLoading = ref(false)
const sentinel = ref<HTMLDivElement>()
let observer: IntersectionObserver | null = null

const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml', 'image/avif']

async function loadMore() {
  if (isLoading.value || !hasMore.value) return
  isLoading.value = true
  try {
    const result = await filesApi.list({ search: search.value || undefined, page: page.value, limit: 20 })
    const filtered = props.imageOnly
      ? result.items.filter(item => item.content_type.startsWith('image/'))
      : result.items
    items.value.push(...filtered)
    hasMore.value = items.value.length < result.total
    page.value++
  } finally {
    isLoading.value = false
  }
}

function reset() {
  items.value = []
  page.value = 1
  hasMore.value = true
}

watch(debouncedSearch, () => { reset(); loadMore() })

onMounted(() => {
  loadMore()
  observer = new IntersectionObserver(entries => {
    if (entries[0].isIntersecting) loadMore()
  }, { threshold: 0.1 })
  if (sentinel.value) observer.observe(sentinel.value)
})

onUnmounted(() => {
  observer?.disconnect()
})

function isImage(item: FileItem) {
  return IMAGE_TYPES.includes(item.content_type)
}

function selectItem(item: FileItem) {
  emit('select', {
    url: item.url,
    filename: item.filename,
    contentType: item.content_type,
    fileItem: item,
  })
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- Search -->
    <div class="p-3 border-b border-border">
      <Input v-model="search" placeholder="Пошук файлів..." class="h-8 w-full" />
    </div>

    <!-- Grid -->
    <div class="flex-1 overflow-y-auto p-3">
      <div v-if="items.length === 0 && !isLoading" class="flex flex-col items-center justify-center h-40 text-muted-foreground gap-2">
        <FileIcon class="size-8 opacity-30" />
        Файлів не знайдено
      </div>

      <div class="grid grid-cols-3 gap-2">
        <button
          v-for="item in items"
          :key="item.id"
          type="button"
          class="group relative flex flex-col items-center gap-1 p-1 rounded-md border border-transparent hover:border-primary/40 hover:bg-muted/50 transition-colors text-center"
          @click="selectItem(item)"
        >
          <!-- Thumbnail -->
          <div class="w-full aspect-square rounded overflow-hidden bg-muted flex items-center justify-center">
            <img
              v-if="isImage(item)"
              :src="item.url"
              :alt="item.filename"
              class="w-full h-full object-cover"
            />
            <FileIcon v-else class="size-6 text-muted-foreground" />
          </div>
          <!-- Filename -->
          <span class="text-xs text-muted-foreground truncate w-full leading-tight">
            {{ item.filename }}
          </span>
          <span class="text-xs text-muted-foreground/60">
            {{ formatSize(item.size_bytes) }}
          </span>
        </button>
      </div>

      <!-- Sentinel + loader -->
      <div ref="sentinel" class="h-8 mt-2 flex justify-center">
        <Spinner v-if="isLoading" class="!size-5" />
      </div>
    </div>
  </div>
</template>
