<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { AttachmentResult, AttachChannelProps, AttachChannelEmits } from '@/core/attachmentChannels/types'
import { filesApi, type FileItem } from '@/core/api/files'
import { useFileList, type FileCategory } from '@/core/composables/useFileList'
import { useDebounce } from '@/core/composables/useDebounce'
import { useToast } from '@/core/composables/useToast'
import { isImageType, formatFileSize, extractFileId } from '@/core/fileUtils'
import {
  File as FileIcon,
  Search,
  UploadCloud,
  Trash2,
  Check,
  AlertCircle,
} from '@lucide/vue'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { Skeleton } from '@/components/ui/skeleton'

const props = defineProps<AttachChannelProps>()
const emit = defineEmits<AttachChannelEmits>()

const { t } = useI18n()
const toast = useToast()

// ── Filters / sorting ──────────────────────────────────────────────────
const search = ref('')
const debouncedSearch = useDebounce(search, 300)
const category = ref<FileCategory>('all')
const scopedToDoc = ref(false)
const sort = ref<'new' | 'name' | 'size'>('new')

const hasDocScope = computed(() => !!props.attachedToDoctype && !!props.attachedToId)
const effectiveCategory = computed<FileCategory>(() =>
  props.imageOnly ? 'image' : category.value,
)
const orderBy = computed(() =>
  sort.value === 'name' ? 'file_name' as const
    : sort.value === 'size' ? 'file_size' as const
      : 'created_at' as const,
)
const order = computed<'asc' | 'desc'>(() => (sort.value === 'name' ? 'asc' : 'desc'))

const categoryTabs: { id: FileCategory; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'image', label: 'Images' },
  { id: 'pdf', label: 'PDF' },
  { id: 'document', label: 'Documents' },
]

const {
  items,
  total,
  isLoading,
  isFetchingNextPage,
  isError,
  hasNextPage,
  fetchNextPage,
  refetch,
} = useFileList({
  search: debouncedSearch,
  category: effectiveCategory,
  scopedToDoc: () => scopedToDoc.value,
  attachedToDoctype: () => props.attachedToDoctype,
  attachedToId: () => props.attachedToId,
  orderBy,
  order,
  pageSize: 30,
})

// ── Infinite scroll ───────────────────────────────────────────────────
const scrollEl = ref<HTMLDivElement>()
const sentinel = ref<HTMLDivElement>()
let observer: IntersectionObserver | null = null

function maybeLoadMore() {
  if (hasNextPage.value && !isFetchingNextPage.value) fetchNextPage()
}

onMounted(() => {
  observer = new IntersectionObserver(
    entries => { if (entries[0].isIntersecting) maybeLoadMore() },
    { root: scrollEl.value ?? null, threshold: 0.1 },
  )
  if (sentinel.value) observer.observe(sentinel.value)
  window.addEventListener('paste', onPaste)
})

onUnmounted(() => {
  observer?.disconnect()
  window.removeEventListener('paste', onPaste)
})

// ── Selection ─────────────────────────────────────────────────────────
const selectedIds = ref<Set<string>>(new Set())
const currentFileId = computed(() =>
  props.currentUrl ? extractFileId(props.currentUrl) : null,
)

function toResult(item: FileItem): AttachmentResult {
  return {
    url: item.url,
    filename: item.filename,
    contentType: item.content_type,
    fileItem: item,
  }
}

function onItemClick(item: FileItem) {
  if (props.multiple) {
    const next = new Set(selectedIds.value)
    next.has(item.id) ? next.delete(item.id) : next.add(item.id)
    selectedIds.value = next
    return
  }
  emit('select', toResult(item))
}

function confirmMany() {
  const picked = items.value.filter(i => selectedIds.value.has(i.id))
  if (picked.length) emit('selectMany', picked.map(toResult))
}

// ── Keyboard navigation across the grid ───────────────────────────────
const COLS = 3
function onGridKeydown(e: KeyboardEvent) {
  const active = document.activeElement as HTMLElement | null
  const idx = Number(active?.dataset.idx ?? -1)
  if (idx < 0) return
  const delta = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: COLS, ArrowUp: -COLS }[e.key]
  if (delta === undefined) return
  e.preventDefault()
  const target = Math.max(0, Math.min(items.value.length - 1, idx + delta))
  scrollEl.value?.querySelector<HTMLElement>(`[data-idx="${target}"]`)?.focus()
}

// ── Upload (drag-drop + clipboard paste) ─────────────────────────────
const isDragging = ref(false)
const isUploading = ref(false)

async function uploadFiles(fileList: FileList | File[]) {
  const files = Array.from(fileList).filter(f =>
    !props.imageOnly || f.type.startsWith('image/'),
  )
  if (!files.length) return
  isUploading.value = true
  try {
    const uploaded: FileItem[] = []
    for (const f of files) {
      uploaded.push(await filesApi.upload(f, {
        attachedToDoctype: props.attachedToDoctype,
        attachedToId: props.attachedToId,
      }))
    }
    await refetch()
    const fresh = uploaded.filter(u => !u.deduped).length
    const dupes = uploaded.length - fresh
    if (fresh) toast.success(t('{n} file(s) uploaded').replace('{n}', String(fresh)))
    if (dupes) toast.info(t('{n} file(s) were already in the library').replace('{n}', String(dupes)))
    if (!props.multiple && uploaded.length === 1) {
      emit('select', toResult(uploaded[0]))
    } else if (props.multiple) {
      const next = new Set(selectedIds.value)
      uploaded.forEach(u => next.add(u.id))
      selectedIds.value = next
    }
  } catch {
    toast.error(t('Upload failed'))
  } finally {
    isUploading.value = false
  }
}

function onDrop(e: DragEvent) {
  isDragging.value = false
  if (e.dataTransfer?.files?.length) uploadFiles(e.dataTransfer.files)
}

function onPaste(e: ClipboardEvent) {
  const files = Array.from(e.clipboardData?.items ?? [])
    .filter(i => i.kind === 'file')
    .map(i => i.getAsFile())
    .filter((f): f is File => !!f)
  if (files.length) uploadFiles(files)
}

// ── Delete ────────────────────────────────────────────────────────────
const deletingId = ref<string | null>(null)

async function removeItem(item: FileItem) {
  if (!window.confirm(t('Delete this file from the library?'))) return
  deletingId.value = item.id
  try {
    await filesApi.delete(item.id)
    selectedIds.value.delete(item.id)
    await refetch()
    toast.success(t('File deleted'))
  } catch {
    toast.error(t('Could not delete the file'))
  } finally {
    deletingId.value = null
  }
}

// Reset selection whenever the result set changes shape.
watch([debouncedSearch, effectiveCategory, scopedToDoc, sort], () => {
  selectedIds.value = new Set()
})

function tooltipFor(item: FileItem) {
  const parts = [item.filename, formatFileSize(item.size_bytes)]
  if (item.created_at) parts.push(new Date(item.created_at).toLocaleString())
  if (item.uploaded_by) parts.push(item.uploaded_by)
  return parts.join(' · ')
}
</script>

<template>
  <div
    class="relative flex h-full flex-col"
    @dragover.prevent="isDragging = true"
    @dragleave.prevent="isDragging = false"
    @drop.prevent="onDrop"
  >
    <!-- Drop overlay -->
    <div
      v-if="isDragging"
      class="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-background/70 border-2 border-dashed border-primary rounded-md"
    >
      <div class="flex flex-col items-center gap-2 text-primary">
        <UploadCloud class="size-8" />
        <span class="text-sm font-medium">{{ t('Drop files to upload') }}</span>
      </div>
    </div>

    <!-- Toolbar -->
    <div class="flex flex-col gap-2 border-b border-border p-3">
      <div class="relative">
        <Search class="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input v-model="search" :placeholder="t('Search files…')" class="h-8 w-full pl-8" />
      </div>

      <div class="flex items-center gap-2">
        <!-- Category chips (hidden when the field is locked to images) -->
        <div v-if="!imageOnly" class="flex gap-1">
          <button
            v-for="tab in categoryTabs"
            :key="tab.id"
            type="button"
            class="rounded px-2 py-1 text-xs transition-colors"
            :class="category === tab.id
              ? 'bg-primary/10 text-primary font-medium'
              : 'text-muted-foreground hover:bg-muted'"
            @click="category = tab.id"
          >
            {{ t(tab.label) }}
          </button>
        </div>

        <select
          v-model="sort"
          class="ml-auto h-7 rounded-md border border-input bg-transparent px-2 text-xs outline-none"
        >
          <option value="new">{{ t('Newest') }}</option>
          <option value="name">{{ t('Name') }}</option>
          <option value="size">{{ t('Size') }}</option>
        </select>
      </div>

      <label
        v-if="hasDocScope"
        class="flex items-center gap-1.5 text-xs text-muted-foreground"
      >
        <input v-model="scopedToDoc" type="checkbox" class="size-3.5 accent-primary" />
        {{ t('Only files from this document') }}
      </label>
    </div>

    <!-- Grid -->
    <div
      ref="scrollEl"
      class="flex-1 overflow-y-auto p-3"
      @keydown="onGridKeydown"
    >
      <!-- First-load skeleton -->
      <div v-if="isLoading" class="grid grid-cols-3 gap-2">
        <Skeleton v-for="i in 9" :key="i" class="aspect-square w-full rounded" />
      </div>

      <!-- Error -->
      <div
        v-else-if="isError"
        class="flex h-40 flex-col items-center justify-center gap-2 text-muted-foreground"
      >
        <AlertCircle class="size-8 opacity-40" />
        <span class="text-xs">{{ t('Failed to load files') }}</span>
        <button
          type="button"
          class="text-xs text-primary hover:underline"
          @click="refetch()"
        >
          {{ t('Try again') }}
        </button>
      </div>

      <!-- Empty -->
      <div
        v-else-if="items.length === 0"
        class="flex h-40 flex-col items-center justify-center gap-2 text-muted-foreground"
      >
        <FileIcon class="size-8 opacity-30" />
        <span class="text-xs">{{ t('No files found') }}</span>
      </div>

      <!-- Results -->
      <div v-else class="grid grid-cols-3 gap-2">
        <button
          v-for="(item, idx) in items"
          :key="item.id"
          type="button"
          :data-idx="idx"
          :tabindex="idx === 0 ? 0 : -1"
          :title="tooltipFor(item)"
          :aria-pressed="multiple ? selectedIds.has(item.id) : undefined"
          class="group relative flex flex-col items-center gap-1 rounded-md border p-1 text-center transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          :class="(multiple && selectedIds.has(item.id))
            ? 'border-primary bg-primary/5'
            : 'border-transparent hover:border-primary/40 hover:bg-muted/50'"
          @click="onItemClick(item)"
        >
          <!-- Thumbnail -->
          <div class="flex aspect-square w-full items-center justify-center overflow-hidden rounded bg-muted">
            <img
              v-if="isImageType(item.content_type)"
              :src="item.url"
              :alt="item.filename"
              loading="lazy"
              class="h-full w-full object-cover"
            />
            <FileIcon v-else class="size-6 text-muted-foreground" />
          </div>

          <span class="w-full truncate leading-tight text-muted-foreground">{{ item.filename }}</span>
          <span class="text-muted-foreground/60">{{ formatFileSize(item.size_bytes) }}</span>

          <!-- "Currently attached" badge -->
          <span
            v-if="currentFileId && item.id === currentFileId"
            class="absolute left-1 top-1 rounded-full bg-primary p-0.5 text-primary-foreground"
            :title="t('Currently attached')"
          >
            <Check class="size-3" />
          </span>

          <!-- Multi-select tick -->
          <span
            v-else-if="multiple && selectedIds.has(item.id)"
            class="absolute left-1 top-1 rounded-full bg-primary p-0.5 text-primary-foreground"
          >
            <Check class="size-3" />
          </span>

          <!-- Delete -->
          <span
            role="button"
            :aria-label="t('Delete file')"
            class="absolute right-1 top-1 rounded bg-background/80 p-1 text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100 focus-visible:opacity-100"
            @click.stop="removeItem(item)"
          >
            <Spinner v-if="deletingId === item.id" class="!size-3" />
            <Trash2 v-else class="size-3" />
          </span>
        </button>
      </div>

      <!-- Sentinel + next-page loader -->
      <div ref="sentinel" class="mt-2 flex h-8 justify-center">
        <Spinner v-if="isFetchingNextPage" class="!size-5" />
      </div>
    </div>

    <!-- Multi-select footer -->
    <div
      v-if="multiple"
      class="flex items-center justify-between border-t border-border px-3 py-2 text-xs"
    >
      <span class="text-muted-foreground">
        {{ t('{n} selected').replace('{n}', String(selectedIds.size)) }}
        <span v-if="total" class="opacity-60"> / {{ total }}</span>
      </span>
      <button
        type="button"
        class="rounded-md bg-primary px-3 py-1 font-medium text-primary-foreground disabled:opacity-50"
        :disabled="selectedIds.size === 0"
        @click="confirmMany"
      >
        {{ t('Attach') }}
      </button>
    </div>

    <div
      v-if="isUploading"
      class="flex items-center justify-center gap-2 border-t border-border py-2 text-xs text-muted-foreground"
    >
      <Spinner class="!size-4" /> {{ t('Uploading…') }}
    </div>
  </div>
</template>
