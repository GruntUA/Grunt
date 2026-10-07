<script setup lang="ts">
/**
 * An Explorer-style browser of the personal file spaces (FileFolder + File):
 * navigation pane, back / forward / up with an address bar, a command bar
 * («Create»: folder, files / a folder from the computer, camera, a link;
 * cut / copy / paste, rename, delete), the open folder's
 * contents as a details list or tiles, and a status bar.
 *
 * Selection works like Explorer: click, Ctrl+click, Shift+click, Ctrl+A;
 * double-click opens. Keys: Ctrl+X / C / V, F2, Delete, Alt+← / → / ↑,
 * Backspace. Dragging items onto a folder moves them (Ctrl - copies); files
 * dragged in from the desktop are uploaded there.
 *
 * - `mode="folder"` - choosing a destination: `target` is the one selected
 *   subfolder, else the open folder (FolderPickerDialog).
 * - `mode="file"` - choosing files: `selection` holds the selected files,
 *   `activate` fires on a double-click (the attach picker).
 *
 * The search box looks through every file the user can see, by name - not
 * only the folders (attachments of documents too).
 *
 * Slots: `actions` (extra command-bar buttons), `footer` (the host's buttons).
 */
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  ArrowLeft, ArrowRight, ArrowUp, Camera, Check, ChevronDown, ChevronRight, ClipboardPaste, Copy,
  File as FileIcon, FileImage, FileText, Folder, FolderOpen, FolderPlus, FolderUp, House, LayoutGrid, Link,
  List, Plus, RefreshCw, Scissors, Search, TextCursorInput, Trash2, Upload, Users,
} from '@lucide/vue'
import { docsApi, type TreeNode } from '@/core/api/docs'
import { filesApi, type FileItem } from '@/core/api/files'
import { fileClipboard } from '@/core/composables/useFolderPicker'
import { useToast } from '@/core/composables/useToast'
import { formatFileSize, fileTypeLabel, isImageType, previewUrl } from '@/core/fileUtils'
import { formatDateTime } from '@/core/datetime'
import { useAuthStore } from '@/stores/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import CameraCapture from '@/components/files/CameraCapture.vue'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

const DT = 'FileFolder'
const DRAG_MIME = 'application/x-grunt-explorer'

const props = withDefaults(defineProps<{
  mode?: 'folder' | 'file'
  /** The folder to open first; «My files» when omitted. */
  folder?: string | null
  /** File mode: pick several files. */
  multiple?: boolean
  /** File mode: show images only. */
  imageOnly?: boolean
  /** Bytes about to be added - the quota bar warns when they don't fit. */
  incomingSize?: number
  /** Initial look of the contents pane. */
  view?: 'details' | 'tiles'
  /** «Create» offers uploads (files, a folder, camera, a link) and desktop files can be dropped in. */
  uploads?: boolean
  /** A file (id) in `folder` to select and scroll to on opening - the one being replaced. */
  focusFile?: string | null
}>(), { mode: 'folder', folder: null, view: 'details', incomingSize: 0, uploads: true })

const emit = defineEmits<{
  /** Folder mode: where things would go now. */
  'update:target': [folder: string, title: string]
  /** File mode: the selected files. */
  'update:selection': [files: FileItem[]]
  /** File mode: a file was double-clicked (or Enter). */
  activate: [file: FileItem]
}>()

const { t } = useI18n()
const toast = useToast()
const auth = useAuthStore()
const me = computed(() => auth.user?.email ?? '')

// Folder tree (navigation pane), loaded a level at a time
const childrenOf = reactive(new Map<string, TreeNode[]>()) // '' -> roots
const nodes = reactive(new Map<string, TreeNode>())
const expanded = reactive(new Set<string>())

async function loadChildren(parent: string) {
  const list = await docsApi.getTreeChildren(DT, parent || null)
  for (const n of list) nodes.set(n.name, n)
  childrenOf.set(parent, list)
  return list
}

function isOwnHome(node: TreeNode | undefined) {
  return !!node?.is_home && node.space_user === me.value
}

function title(node: TreeNode | undefined): string {
  if (!node) return ''
  if (isOwnHome(node)) return t('My files')
  return String(node.display_title || node.folder_name || node.name)
}

interface NavRow { node: TreeNode; depth: number }
const navRows = computed<NavRow[]>(() => {
  const out: NavRow[] = []
  const walk = (parent: string, depth: number) => {
    for (const node of childrenOf.get(parent) ?? []) {
      out.push({ node, depth })
      if (expanded.has(node.name)) walk(node.name, depth + 1)
    }
  }
  walk('', 0)
  return out
})

async function toggle(node: TreeNode) {
  if (expanded.has(node.name)) {
    expanded.delete(node.name)
    return
  }
  if (!childrenOf.has(node.name)) await loadChildren(node.name)
  expanded.add(node.name)
}

// The open folder: path, contents, history
const current = ref<string>('')
const path = ref<TreeNode[]>([])
const files = ref<FileItem[]>([])
const loading = ref(false)
const viewMode = ref(props.view)
const history = reactive({ stack: [] as string[], index: -1 })

const subfolders = computed(() => childrenOf.get(current.value) ?? [])

// Search: every file the user can see, by name; null when not searching
const query = ref('')
const results = ref<FileItem[] | null>(null)
let searchTimer: ReturnType<typeof setTimeout> | undefined

watch(query, (q) => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => search(q), 300)
})

async function search(q: string) {
  const text = q.trim()
  if (!text) {
    results.value = null
    return
  }
  loading.value = true
  try {
    const res = await filesApi.list({
      search: text,
      contentTypeLike: props.imageOnly ? 'image/' : undefined,
      orderBy: 'created_at',
      order: 'desc',
      limit: 200,
    })
    if (query.value.trim() === text) {
      results.value = res.items
      selected.value = new Set()
    }
  } catch (err) {
    toast.error(errorText(err))
  } finally {
    loading.value = false
  }
}

/** Folders and files of the open folder (or the search results) as one list - `d:<name>` / `f:<id>` keys. */
interface Entry { key: string; folder?: TreeNode; file?: FileItem }
const entries = computed<Entry[]>(() => results.value
  ? results.value.map((file) => ({ key: `f:${file.id}`, file }))
  : [
      ...subfolders.value.map((folder) => ({ key: `d:${folder.name}`, folder })),
      ...files.value.map((file) => ({ key: `f:${file.id}`, file })),
    ])

async function open(folder: string, { record = true } = {}) {
  if (!folder) return
  query.value = ''
  results.value = null
  loading.value = true
  editing.value = null
  confirmingDelete.value = false
  try {
    if (!nodes.has(folder)) nodes.set(folder, await docsApi.get(DT, folder) as TreeNode)
    const [ancestors] = await Promise.all([
      docsApi.getTreeAncestors(DT, folder),
      loadChildren(folder),
      loadFiles(folder),
    ])
    for (const a of ancestors) nodes.set(a.name, { ...nodes.get(a.name), ...a })
    path.value = [...ancestors, nodes.get(folder)!]
    current.value = folder
    selected.value = new Set()
    // Keep the navigation pane in step: unfold the way down to this folder.
    for (const a of ancestors) {
      if (!childrenOf.has(a.name)) await loadChildren(a.name)
      expanded.add(a.name)
    }
    if (record) {
      history.stack.splice(history.index + 1, Infinity, folder)
      history.index = history.stack.length - 1
    }
  } catch (err) {
    toast.error(errorText(err))
  } finally {
    loading.value = false
  }
}

async function loadFiles(folder: string) {
  const res = await filesApi.list({
    folder,
    contentTypeLike: props.imageOnly ? 'image/' : undefined,
    orderBy: 'file_name',
    order: 'asc',
    limit: 500,
  })
  files.value = res.items
}

const canBack = computed(() => history.index > 0)
const canForward = computed(() => history.index < history.stack.length - 1)
const parentOfCurrent = computed(() => path.value.at(-2)?.name ?? null)

function back() {
  if (!canBack.value) return
  history.index--
  open(history.stack[history.index], { record: false })
}
function forward() {
  if (!canForward.value) return
  history.index++
  open(history.stack[history.index], { record: false })
}
function up() {
  if (parentOfCurrent.value) open(parentOfCurrent.value)
}

/** Re-read everything on screen - after a command changed the folders. */
async function reload() {
  await Promise.all([...childrenOf.keys()].map(loadChildren))
  await Promise.all([loadFiles(current.value), loadUsage(), results.value ? search(query.value) : null])
  const keys = new Set(entries.value.map((e) => e.key))
  selected.value = new Set([...selected.value].filter((k) => keys.has(k)))
}

// Selection
const selected = ref<Set<string>>(new Set())
let anchor: string | null = null

const selectedFolders = computed(() => entries.value.filter((e) => e.folder && selected.value.has(e.key)).map((e) => e.folder!))
const selectedFiles = computed(() => entries.value.filter((e) => e.file && selected.value.has(e.key)).map((e) => e.file!))
const target = computed(() =>
  selected.value.size === 1 && selectedFolders.value.length === 1 ? selectedFolders.value[0].name : current.value,
)

watch(target, (folder) => {
  if (folder) emit('update:target', folder, title(nodes.get(folder)))
})
watch(selectedFiles, (list) => emit('update:selection', props.multiple ? list : list.slice(-1)))

function select(e: MouseEvent, key: string) {
  const next = new Set(e.ctrlKey || e.metaKey ? selected.value : [])
  if (e.shiftKey && anchor) {
    const keys = entries.value.map((x) => x.key)
    const [a, b] = [keys.indexOf(anchor), keys.indexOf(key)].sort((x, y) => x - y)
    for (const k of keys.slice(a, b + 1)) next.add(k)
  } else if ((e.ctrlKey || e.metaKey) && next.has(key)) {
    next.delete(key)
  } else {
    next.add(key)
    anchor = key
  }
  selected.value = next
}

function openEntry(entry: Entry) {
  if (entry.folder) open(entry.folder.name)
  else if (entry.file && props.mode === 'file') emit('activate', entry.file)
  else if (entry.file) window.open(entry.file.url, '_blank', 'noopener')
}

// New folder / rename - typed in place, like Explorer
const editing = ref<{ key: string | null; value: string } | null>(null) // key null = new folder
const editInput = ref<InstanceType<typeof Input>[] | InstanceType<typeof Input> | null>(null)

async function startEdit(key: string | null, value: string) {
  editing.value = { key, value }
  await nextTick()
  focusEdit()
}

function focusEdit() {
  const edit = editing.value
  const inputs = Array.isArray(editInput.value) ? editInput.value : [editInput.value]
  const el = (inputs[0]?.$el ?? null) as HTMLInputElement | null
  if (!edit || !el) return
  el.focus()
  // Rename selects the name without its extension, like Explorer.
  const dot = edit.key?.startsWith('f:') ? edit.value.lastIndexOf('.') : -1
  el.setSelectionRange(0, dot > 0 ? dot : edit.value.length)
}

function startCreate() {
  selected.value = new Set()
  startEdit(null, t('New folder'))
}

function startRename() {
  const [entry] = entries.value.filter((e) => selected.value.has(e.key))
  if (!entry || selected.value.size !== 1) return
  startEdit(entry.key, entry.folder ? title(entry.folder) : entry.file!.filename)
}

async function commitEdit() {
  const edit = editing.value
  if (!edit) return // Enter already did it; this is the blur that follows
  editing.value = null
  const name = edit.value.trim()
  if (!name) return
  try {
    if (edit.key === null) {
      const doc = await docsApi.create(DT, { folder_name: name, parent_folder: current.value })
      await loadChildren(current.value)
      expanded.add(current.value)
      selected.value = new Set([`d:${doc.name}`])
    } else if (edit.key.startsWith('d:')) {
      await docsApi.update(DT, edit.key.slice(2), { folder_name: name })
      await reload()
    } else {
      await docsApi.update('File', edit.key.slice(2), { file_name: name })
      await reload()
    }
  } catch (err) {
    toast.error(errorText(err))
  }
}

// Clipboard, delete, move
const busy = ref(false)
const hasSelection = computed(() => selected.value.size > 0)

function itemsOf(keys: Iterable<string>) {
  const list = [...keys]
  return {
    files: list.filter((k) => k.startsWith('f:')).map((k) => k.slice(2)),
    folders: list.filter((k) => k.startsWith('d:')).map((k) => k.slice(2)),
  }
}

function toClipboard(mode: 'cut' | 'copy') {
  if (!hasSelection.value) return
  Object.assign(fileClipboard, { mode, ...itemsOf(selected.value) })
}

const isCut = (key: string) =>
  fileClipboard.mode === 'cut'
  && (key.startsWith('d:') ? fileClipboard.folders : fileClipboard.files).includes(key.slice(2))

async function run(work: () => Promise<unknown>) {
  busy.value = true
  try {
    await work()
  } catch (err) {
    toast.error(errorText(err))
  } finally {
    busy.value = false
    await reload()
  }
}

function paste() {
  if (!fileClipboard.mode || !current.value) return
  const items = { files: [...fileClipboard.files], folders: [...fileClipboard.folders] }
  if (fileClipboard.mode === 'cut') {
    Object.assign(fileClipboard, { mode: null, files: [], folders: [] })
    return run(() => moveItems(items, current.value))
  }
  return run(() => filesApi.copyItems(current.value, items))
}

/** Move files and folders into *folder* - one save each, so every rule applies. */
async function moveItems(items: { files: string[]; folders: string[] }, folder: string) {
  const errors: string[] = []
  for (const id of items.files) {
    await docsApi.update('File', id, { folder }).catch((err) => errors.push(errorText(err)))
  }
  for (const id of items.folders) {
    if (id === folder) continue
    await docsApi.moveTreeNode(DT, id, folder).catch((err) => errors.push(errorText(err)))
  }
  if (errors.length) toast.error(errors[0], t('Not moved: {n}', { n: String(errors.length) }))
}

const confirmingDelete = ref(false)

function askDelete() {
  if (hasSelection.value) confirmingDelete.value = true
}

function confirmDelete() {
  confirmingDelete.value = false
  const items = itemsOf(selected.value)
  return run(() => filesApi.deleteItems(items))
}

// Drag & drop: onto a folder moves (Ctrl - copies)
const dropTarget = ref<string | null>(null)

function onDragStart(e: DragEvent, key: string) {
  if (!selected.value.has(key)) selected.value = new Set([key])
  e.dataTransfer?.setData(DRAG_MIME, JSON.stringify([...selected.value]))
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'copyMove'
}

const desktopFiles = (e: DragEvent) => props.uploads && !!e.dataTransfer?.types.includes('Files')

function onDragOver(e: DragEvent, folder: string) {
  const ours = !!e.dataTransfer?.types.includes(DRAG_MIME)
  if (!ours && !desktopFiles(e)) return
  e.preventDefault()
  e.stopPropagation()
  e.dataTransfer!.dropEffect = ours && !e.ctrlKey ? 'move' : 'copy'
  dropTarget.value = folder
}

function onDrop(e: DragEvent, folder: string) {
  dropTarget.value = null
  if (desktopFiles(e) && e.dataTransfer?.files.length) {
    e.preventDefault()
    e.stopPropagation()
    return uploadFiles(Array.from(e.dataTransfer.files), folder)
  }
  const raw = e.dataTransfer?.getData(DRAG_MIME)
  if (!raw) return
  e.preventDefault()
  const items = itemsOf(JSON.parse(raw) as string[])
  items.folders = items.folders.filter((id) => id !== folder)
  if (!items.files.length && !items.folders.length) return
  return run(() => (e.ctrlKey ? filesApi.copyItems(folder, items) : moveItems(items, folder)))
}

// Uploads: files / a whole folder from the computer, the camera, a link
const filesInput = ref<HTMLInputElement | null>(null)
const dirInput = ref<HTMLInputElement | null>(null)
const cameraInput = ref<HTMLInputElement | null>(null)
const cameraOpen = ref(false)

/** The webcam inside the explorer; without camera access in the browser - the device's own picker. */
function openCamera() {
  if ('mediaDevices' in navigator && 'getUserMedia' in navigator.mediaDevices) cameraOpen.value = true
  else cameraInput.value?.click()
}

async function onCaptured(file: File) {
  cameraOpen.value = false
  await uploadFiles([file], current.value)
}
const uploading = ref<{ done: number; total: number } | null>(null)

function onPicked(e: Event) {
  const input = e.target as HTMLInputElement
  const picked = Array.from(input.files ?? [])
  input.value = ''
  if (picked.length) uploadFiles(picked, current.value)
}

/**
 * Upload *list* into *folder*. A file picked with its folder
 * (`webkitRelativePath` = «Docs/2026/a.pdf») recreates that folder tree.
 */
async function uploadFiles(list: File[], folder: string) {
  if (!folder || !list.length) return
  uploading.value = { done: 0, total: list.length }
  const madeFolders = new Map<string, string>() // relative path -> FileFolder name
  const uploaded: string[] = []
  const failed: string[] = []

  async function folderFor(relative: string): Promise<string> {
    const parts = relative.split('/').slice(0, -1)
    let parent = folder
    for (let i = 0; i < parts.length; i++) {
      const key = parts.slice(0, i + 1).join('/')
      if (!madeFolders.has(key)) {
        const doc = await docsApi.create(DT, { folder_name: parts[i], parent_folder: parent })
        madeFolders.set(key, String(doc.name))
      }
      parent = madeFolders.get(key)!
    }
    return parent
  }

  for (const file of list) {
    try {
      const into = file.webkitRelativePath ? await folderFor(file.webkitRelativePath) : folder
      const item = await filesApi.upload(file, { folder: into })
      if (into === current.value) uploaded.push(item.id)
    } catch (err) {
      failed.push(`${file.name}: ${errorText(err)}`)
    }
    uploading.value = { done: uploading.value.done + 1, total: list.length }
  }
  uploading.value = null
  if (failed.length) toast.error(failed[0], t('Not uploaded: {n}', { n: String(failed.length) }))
  await reload()
  if (uploaded.length) await selectFiles(uploaded)
  const top = [...madeFolders.entries()].filter(([path]) => !path.includes('/')).map(([, name]) => `d:${name}`)
  if (top.length) selected.value = new Set([...selected.value, ...top])
}

// From a link - typed into a bar under the command bar
const linkOpen = ref(false)
const linkUrl = ref('')
const linkBusy = ref(false)
const linkInput = ref<InstanceType<typeof Input> | null>(null)

async function startLink() {
  linkUrl.value = ''
  linkOpen.value = true
  await nextTick()
  focusLink()
}

const focusLink = () => (linkInput.value?.$el as HTMLInputElement | undefined)?.focus()

/** The «Create» menu hands focus back to its button once closed - send it to what the item opened. */
function onMenuClosed(e: Event) {
  e.preventDefault()
  if (editing.value) focusEdit()
  else if (linkOpen.value) focusLink()
}

async function commitLink() {
  const url = linkUrl.value.trim()
  if (!url || linkBusy.value) return
  linkBusy.value = true
  try {
    const item = await filesApi.uploadFromUrl(url, current.value)
    linkOpen.value = false
    await reload()
    await selectFiles([item.id])
  } catch (err) {
    toast.error(errorText(err), t('Could not download the file'))
  } finally {
    linkBusy.value = false
  }
}

// Quota of «My files»
const usage = ref<{ used: number; quota: number | null } | null>(null)
const usagePercent = computed(() =>
  usage.value?.quota ? Math.min(100, Math.round((usage.value.used / usage.value.quota) * 100)) : 0,
)
async function loadUsage() {
  usage.value = await filesApi.storageUsage().catch(() => null)
}
const overQuota = computed(() =>
  !!usage.value?.quota && usage.value.used + props.incomingSize > usage.value.quota,
)

/** Select files that just arrived (e.g. uploaded here). */
async function selectFiles(ids: string[]) {
  await Promise.all([loadFiles(current.value), loadUsage()])
  const keys = ids.map((id) => `f:${id}`)
  selected.value = new Set(props.multiple ? [...selected.value, ...keys] : keys.slice(-1))
}

async function start() {
  history.stack = []
  history.index = -1
  childrenOf.clear()
  expanded.clear()
  const [home] = await Promise.all([filesApi.homeFolder(), loadChildren(''), loadUsage()])
  if (!childrenOf.get('')?.some((n) => n.name === home.name)) await loadChildren('')
  await open(props.folder || home.name)
  if (props.focusFile && files.value.some((f) => f.id === props.focusFile)) {
    const key = `f:${props.focusFile}`
    selected.value = new Set([key])
    anchor = key
    await nextTick()
    document.querySelector(`[data-key="${CSS.escape(key)}"]`)?.scrollIntoView({ block: 'center' })
  }
}
start()

function onKeydown(e: KeyboardEvent) {
  if (editing.value || e.target instanceof HTMLInputElement) return
  const mod = e.ctrlKey || e.metaKey
  const key = e.key.toLowerCase()
  if (e.altKey && e.key === 'ArrowLeft') back()
  else if (e.altKey && e.key === 'ArrowRight') forward()
  else if (e.altKey && e.key === 'ArrowUp') up()
  else if (e.key === 'Backspace') up()
  else if (mod && key === 'a') selected.value = new Set(entries.value.map((x) => x.key))
  else if (mod && key === 'x') toClipboard('cut')
  else if (mod && key === 'c') toClipboard('copy')
  else if (mod && key === 'v') paste()
  else if (e.key === 'F2') startRename()
  else if (e.key === 'Delete') askDelete()
  else if (e.key === 'Enter' && selected.value.size === 1) {
    const entry = entries.value.find((x) => selected.value.has(x.key))
    if (entry) openEntry(entry)
  } else return
  e.preventDefault()
}

function fileIcon(f: FileItem) {
  if (isImageType(f.content_type)) return FileImage
  if (f.content_type?.startsWith('text/') || /pdf|word|document/.test(f.content_type ?? '')) return FileText
  return FileIcon
}

function errorText(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail) return String(detail.message)
  return err instanceof Error ? err.message : t('Something went wrong')
}

defineExpose({ current, reload, selectFiles, usage })

const ROW = 'grid w-full grid-cols-[minmax(0,1fr)_9rem_5rem_5rem] items-center gap-3 px-4 py-1.5 text-left'
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col outline-none" tabindex="-1" @keydown="onKeydown">
    <!-- Address bar -->
    <div class="flex items-center gap-1 border-t px-2 py-1.5">
      <Button variant="ghost" size="icon" class="size-8" :disabled="!canBack" :title="t('Back')" @click="back">
        <ArrowLeft />
      </Button>
      <Button variant="ghost" size="icon" class="size-8" :disabled="!canForward" :title="t('Forward')" @click="forward">
        <ArrowRight />
      </Button>
      <Button variant="ghost" size="icon" class="size-8" :disabled="!parentOfCurrent" :title="t('Up')" @click="up">
        <ArrowUp />
      </Button>
      <nav class="flex h-8 min-w-0 flex-1 items-center gap-0.5 overflow-hidden rounded-md border bg-background px-1.5"
        :aria-label="t('Folder path')">
        <template v-if="results">
          <Search class="size-4 shrink-0 text-muted-foreground" />
          <span class="truncate px-1.5">{{ t('Search results for «{q}»', { q: query.trim() }) }}</span>
        </template>
        <component :is="isOwnHome(path[0]) ? House : Users" v-else class="size-4 shrink-0 text-muted-foreground" />
        <template v-for="(node, i) in results ? [] : path" :key="node.name">
          <ChevronRight v-if="i > 0" class="size-3.5 shrink-0 text-muted-foreground" />
          <button type="button" class="truncate rounded px-1.5 py-0.5 hover:bg-accent"
            :class="[i === path.length - 1 && 'font-medium', dropTarget === node.name && 'ring-2 ring-primary']"
            @click="open(node.name)"
            @dragover="onDragOver($event, node.name)" @dragleave="dropTarget = null" @drop="onDrop($event, node.name)">
            {{ title(node) }}
          </button>
        </template>
      </nav>
      <Button variant="ghost" size="icon" class="size-8" :title="t('Refresh')" @click="reload">
        <RefreshCw :class="(loading || busy) && 'animate-spin'" />
      </Button>
      <div class="relative w-64 shrink-0">
        <Search class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input v-model="query" type="search" class="h-8 pl-8" :placeholder="t('Search all files')"
          :aria-label="t('Search all files')" @keydown.esc="query && ($event.stopPropagation(), query = '')" />
      </div>
    </div>

    <!-- Command bar -->
    <div class="flex flex-wrap items-center gap-0.5 border-y bg-muted/30 px-2 py-1">
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <Button variant="ghost" size="sm" class="h-8">
            <Plus />{{ t('Create') }}<ChevronDown class="text-muted-foreground" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" class="min-w-56" @close-auto-focus="onMenuClosed">
          <DropdownMenuItem @select="startCreate"><FolderPlus />{{ t('Folder') }}</DropdownMenuItem>
          <template v-if="uploads">
            <DropdownMenuSeparator />
            <DropdownMenuItem @select="filesInput?.click()"><Upload />{{ t('Files from the computer…') }}</DropdownMenuItem>
            <DropdownMenuItem @select="dirInput?.click()"><FolderUp />{{ t('Folder from the computer…') }}</DropdownMenuItem>
            <DropdownMenuItem @select="openCamera"><Camera />{{ t('Photo from the camera') }}</DropdownMenuItem>
            <DropdownMenuItem @select="startLink"><Link />{{ t('From a link…') }}</DropdownMenuItem>
          </template>
        </DropdownMenuContent>
      </DropdownMenu>
      <input ref="filesInput" type="file" multiple class="hidden" :accept="imageOnly ? 'image/*' : undefined" @change="onPicked" />
      <input ref="dirInput" type="file" webkitdirectory class="hidden" @change="onPicked" />
      <input ref="cameraInput" type="file" accept="image/*" capture="environment" class="hidden" @change="onPicked" />
      <span class="mx-1 h-5 w-px bg-border" />
      <Button variant="ghost" size="icon" class="size-8" :disabled="!hasSelection" :title="t('Cut') + ' (Ctrl+X)'"
        @click="toClipboard('cut')">
        <Scissors />
      </Button>
      <Button variant="ghost" size="icon" class="size-8" :disabled="!hasSelection" :title="t('Copy') + ' (Ctrl+C)'"
        @click="toClipboard('copy')">
        <Copy />
      </Button>
      <Button variant="ghost" size="icon" class="size-8" :disabled="!fileClipboard.mode || busy"
        :title="t('Paste') + ' (Ctrl+V)'" @click="paste">
        <ClipboardPaste />
      </Button>
      <Button variant="ghost" size="icon" class="size-8" :disabled="selected.size !== 1" :title="t('Rename') + ' (F2)'"
        @click="startRename">
        <TextCursorInput />
      </Button>
      <Button variant="ghost" size="icon" class="size-8 hover:text-destructive" :disabled="!hasSelection || busy"
        :title="t('Delete') + ' (Delete)'" @click="askDelete">
        <Trash2 />
      </Button>
      <span class="mx-1 h-5 w-px bg-border" />
      <Button variant="ghost" size="icon" class="size-8"
        :title="viewMode === 'tiles' ? t('Details') : t('Tiles')"
        @click="viewMode = viewMode === 'tiles' ? 'details' : 'tiles'">
        <component :is="viewMode === 'tiles' ? List : LayoutGrid" />
      </Button>
      <div class="ml-auto flex items-center gap-0.5">
        <slot name="actions" />
      </div>
    </div>

    <!-- «From a link» -->
    <form v-if="linkOpen" class="flex items-center gap-2 border-b px-3 py-2" @submit.prevent="commitLink">
      <Link class="size-4 shrink-0 text-muted-foreground" />
      <Input ref="linkInput" v-model="linkUrl" type="url" required placeholder="https://…" class="h-8 flex-1"
        :aria-label="t('Link to a file')" :disabled="linkBusy" @keydown.esc.stop.prevent="linkOpen = false" />
      <Button type="submit" size="sm" :disabled="linkBusy">
        <RefreshCw v-if="linkBusy" class="animate-spin" />{{ t('Download') }}
      </Button>
      <Button type="button" variant="ghost" size="sm" @click="linkOpen = false">{{ t('Cancel') }}</Button>
    </form>

    <div class="flex min-h-0 flex-1">
      <!-- Navigation pane -->
      <nav class="hidden w-56 shrink-0 overflow-y-auto border-r p-1.5 sm:block" :aria-label="t('Folders')">
        <div v-for="{ node, depth } in navRows" :key="node.name"
          class="flex items-center rounded-md hover:bg-accent"
          :class="[current === node.name && 'bg-accent font-medium', dropTarget === node.name && 'ring-2 ring-primary']"
          :style="{ paddingLeft: `${depth * 12}px` }"
          @dragover="onDragOver($event, node.name)" @dragleave="dropTarget = null" @drop="onDrop($event, node.name)">
          <button type="button"
            class="flex size-6 shrink-0 items-center justify-center text-muted-foreground"
            :class="!node.has_children && 'invisible'"
            :aria-label="expanded.has(node.name) ? t('Collapse') : t('Expand')"
            @click="toggle(node)">
            <ChevronRight class="size-3.5 transition-transform" :class="expanded.has(node.name) && 'rotate-90'" />
          </button>
          <button type="button" class="flex min-w-0 flex-1 items-center gap-2 py-1.5 pr-1 text-left" @click="open(node.name)">
            <component
              :is="depth === 0 ? (isOwnHome(node) ? House : Users) : current === node.name ? FolderOpen : Folder"
              class="size-4 shrink-0"
              :class="depth === 0 ? 'text-primary' : 'text-amber-500'" />
            <span class="truncate">{{ title(node) }}</span>
          </button>
        </div>
      </nav>

      <CameraCapture v-if="cameraOpen" @capture="onCaptured" @close="cameraOpen = false" />

      <!-- Contents of the open folder; a click on empty space clears the selection -->
      <div v-else class="min-w-0 flex-1 overflow-y-auto" role="listbox" aria-multiselectable="true"
        :class="dropTarget === current && 'ring-2 ring-inset ring-primary'"
        :aria-label="title(path.at(-1))" @click.self="selected = new Set()"
        @dragover="onDragOver($event, current)" @dragleave.self="dropTarget = null" @drop="onDrop($event, current)">
        <!-- Details -->
        <template v-if="viewMode === 'details'">
          <div class="sticky top-0 z-10 grid grid-cols-[minmax(0,1fr)_9rem_5rem_5rem] gap-3 border-b bg-background px-4 py-1.5 text-muted-foreground">
            <span>{{ t('Name') }}</span>
            <span>{{ t('Date modified') }}</span>
            <span>{{ t('Type') }}</span>
            <span class="text-right">{{ t('Size') }}</span>
          </div>

          <div v-if="editing && editing.key === null" class="flex items-center gap-2 px-4 py-1">
            <Folder class="size-4 shrink-0 text-amber-500" />
            <Input ref="editInput" v-model="editing.value" class="h-7"
              @keydown.enter.prevent="commitEdit" @keydown.esc.stop.prevent="editing = null" @blur="commitEdit" />
          </div>

          <div v-for="entry in entries" :key="entry.key" :data-key="entry.key" role="option" :aria-selected="selected.has(entry.key)"
            :class="[ROW, 'cursor-default select-none hover:bg-accent/60',
                     selected.has(entry.key) && 'bg-accent',
                     isCut(entry.key) && 'opacity-50',
                     entry.folder && dropTarget === entry.folder.name && 'ring-2 ring-inset ring-primary']"
            draggable="true"
            @click="select($event, entry.key)" @dblclick="openEntry(entry)"
            @dragstart="onDragStart($event, entry.key)"
            @dragover="entry.folder && onDragOver($event, entry.folder.name)" @dragleave="dropTarget = null"
            @drop="entry.folder && onDrop($event, entry.folder.name)">
            <span class="flex min-w-0 items-center gap-2">
              <Folder v-if="entry.folder" class="size-4 shrink-0 text-amber-500" />
              <component :is="fileIcon(entry.file!)" v-else class="size-4 shrink-0 text-muted-foreground" />
              <Input v-if="editing && editing.key === entry.key" ref="editInput" v-model="editing.value" class="h-7"
                @click.stop @dblclick.stop
                @keydown.enter.prevent="commitEdit" @keydown.esc.stop.prevent="editing = null" @blur="commitEdit" />
              <span v-else class="truncate">{{ entry.folder ? title(entry.folder) : entry.file!.filename }}</span>
            </span>
            <template v-if="entry.folder">
              <span class="text-muted-foreground">{{ entry.folder.modified_at ? formatDateTime(entry.folder.modified_at as string) : '' }}</span>
              <span class="text-muted-foreground">{{ t('Folder') }}</span>
              <span />
            </template>
            <template v-else>
              <span class="text-muted-foreground">{{ entry.file!.created_at ? formatDateTime(entry.file!.created_at) : '' }}</span>
              <span class="text-muted-foreground">{{ fileTypeLabel(entry.file!.filename, entry.file!.content_type) }}</span>
              <span class="text-right text-muted-foreground">{{ formatFileSize(entry.file!.size_bytes) }}</span>
            </template>
          </div>
        </template>

        <!-- Tiles -->
        <div v-else class="grid grid-cols-[repeat(auto-fill,minmax(7.5rem,1fr))] gap-2 p-3" @click.self="selected = new Set()">
          <div v-if="editing && editing.key === null" class="flex flex-col items-center gap-1 rounded-md p-2">
            <Folder class="size-16 text-amber-500" stroke-width="1.25" />
            <Input ref="editInput" v-model="editing.value" class="h-7"
              @keydown.enter.prevent="commitEdit" @keydown.esc.stop.prevent="editing = null" @blur="commitEdit" />
          </div>
          <div v-for="entry in entries" :key="entry.key" :data-key="entry.key" role="option" :aria-selected="selected.has(entry.key)"
            class="relative flex cursor-default select-none flex-col items-center gap-1 rounded-md p-2 text-center hover:bg-accent/60"
            :class="[selected.has(entry.key) && 'bg-accent ring-2 ring-primary',
                     isCut(entry.key) && 'opacity-50',
                     entry.folder && dropTarget === entry.folder.name && 'ring-2 ring-primary']"
            draggable="true"
            @click="select($event, entry.key)" @dblclick="openEntry(entry)"
            @dragstart="onDragStart($event, entry.key)"
            @dragover="entry.folder && onDragOver($event, entry.folder.name)" @dragleave="dropTarget = null"
            @drop="entry.folder && onDrop($event, entry.folder.name)">
            <Folder v-if="entry.folder" class="size-16 text-amber-500" stroke-width="1.25" />
            <img v-else-if="previewUrl(entry.file!)" :src="previewUrl(entry.file!)!" alt="" loading="lazy" draggable="false"
              class="size-16 rounded object-cover" />
            <component :is="fileIcon(entry.file!)" v-else class="size-16 text-muted-foreground" stroke-width="1.25" />
            <Input v-if="editing && editing.key === entry.key" ref="editInput" v-model="editing.value" class="h-7"
              @click.stop @dblclick.stop
              @keydown.enter.prevent="commitEdit" @keydown.esc.stop.prevent="editing = null" @blur="commitEdit" />
            <span v-else class="line-clamp-2 break-all">{{ entry.folder ? title(entry.folder) : entry.file!.filename }}</span>
            <span v-if="entry.file" class="text-muted-foreground">{{ formatFileSize(entry.file.size_bytes) }}</span>
            <span v-if="selected.has(entry.key)"
              class="absolute right-1.5 top-1.5 flex size-5 items-center justify-center rounded-full bg-primary text-primary-foreground">
              <Check class="size-3.5" />
            </span>
          </div>
        </div>

        <p v-if="!loading && !editing && !entries.length"
          class="px-4 py-10 text-center text-muted-foreground">
          {{ t('This folder is empty') }}
        </p>
      </div>
    </div>

    <!-- Status bar + the host's buttons (or the delete confirmation) -->
    <div class="flex flex-wrap items-center gap-3 border-t px-4 py-3">
      <template v-if="confirmingDelete">
        <span class="text-destructive">
          {{ t('Delete selected: {n}? Folders go with everything in them.', { n: selected.size }) }}
        </span>
        <div class="ml-auto flex gap-2">
          <Button variant="outline" @click="confirmingDelete = false">{{ t('Cancel') }}</Button>
          <Button variant="destructive" @click="confirmDelete">{{ t('Delete') }}</Button>
        </div>
      </template>
      <template v-else>
        <span v-if="uploading" class="flex items-center gap-2 text-muted-foreground">
          <RefreshCw class="size-3.5 animate-spin" />
          {{ t('Uploading {done} of {total}…', { done: uploading.done + 1 > uploading.total ? uploading.total : uploading.done + 1, total: uploading.total }) }}
        </span>
        <span v-else class="text-muted-foreground">
          {{ t('Items: {n}', { n: entries.length }) }}
          <template v-if="selected.size"> · {{ t('Selected: {n}', { n: selected.size }) }}</template>
        </span>
        <div v-if="usage?.quota" class="flex min-w-40 items-center gap-2" :class="overQuota ? 'text-destructive' : 'text-muted-foreground'">
          <div class="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
            <div class="h-full" :class="overQuota ? 'bg-destructive' : 'bg-primary'" :style="{ width: `${usagePercent}%` }" />
          </div>
          <span>{{ t('{used} of {quota} used', { used: formatFileSize(usage.used), quota: formatFileSize(usage.quota) }) }}</span>
        </div>
        <div class="ml-auto flex gap-2">
          <slot name="footer" />
        </div>
      </template>
    </div>
  </div>
</template>
