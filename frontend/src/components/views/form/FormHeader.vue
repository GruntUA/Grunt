<script setup lang="ts">
import { ref, computed, shallowRef } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useQueryClient } from '@tanstack/vue-query'
import type { Component } from 'vue'
import type { DocType, ScriptButton, ScriptMenuItem } from '@/types'
import {
  Loader2,
  EllipsisVertical,
  RefreshCw,
  Share2,
  Copy as CopyIcon,
  Copy,
  Undo,
  History,
  Pencil,
  Trash2,
  ChevronDown,
  PanelRight,
  Database,
  Check,
  HardDriveDownload,
} from '@lucide/vue'
import { metaApi, type DocTypeTableInfo, type DocTypeCompactResult } from '@/core/api/meta'
import { useDocPanel } from '@/components/views/sidebar/useDocPanel'
import AppBreadcrumb from '@/components/app/AppBreadcrumb.vue'
import { resolveStatusBadge } from '@/core/status'
import WorkflowBar from '@/components/views/WorkflowBar.vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { ButtonVariants } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { DropdownMenuSeparator } from '@/components/ui/dropdown-menu'
const props = defineProps<{
  dt: DocType | null
  doctype: string
  id: string | null
  workspace?: string
  docTitle: string
  document: any
  isDirty: boolean
  isLoading: boolean
  isSaving: boolean
  scriptButtons: ScriptButton[]
  scriptMenuItems: ScriptMenuItem[]
  hidePanelToggle?: boolean
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'delete'): void
  (e: 'duplicate'): void
  (e: 'rename', newId: string): void
  (e: 'toggleLog'): void
  (e: 'invalidate'): void
}>()

const { t } = useI18n()
const auth = useAuthStore()
const router = useRouter()
const queryClient = useQueryClient()
const { open: panelOpen, toggle: togglePanel } = useDocPanel()

const shareLink = ref<string | null>(null)
const shareLoading = ref(false)
const showShareDialog = ref(false)
const shareExpires = ref('')
const showRenameDialog = ref(false)
const newDocId = ref('')
const isRenaming = ref(false)

// Table info (DocType editor only)
const isDocTypeEditor = computed(() => props.doctype === 'DocType' && !!props.id)
const showTableInfoDialog = ref(false)
const tableInfo = ref<DocTypeTableInfo | null>(null)
const tableInfoLoading = ref(false)
const tableInfoError = ref('')
const tableNameCopied = ref(false)

// Compaction (VACUUM / OPTIMIZE) — blocking, so it goes through a confirm step
const confirmCompact = ref(false)
const compacting = ref(false)
const compactResult = ref<DocTypeCompactResult | null>(null)
const compactError = ref('')

async function openTableInfo() {
  if (!props.id) return
  showTableInfoDialog.value = true
  tableInfo.value = null
  tableInfoError.value = ''
  confirmCompact.value = false
  compactResult.value = null
  compactError.value = ''
  tableInfoLoading.value = true
  try {
    tableInfo.value = await metaApi.tableInfo(props.id)
  } catch (e: any) {
    tableInfoError.value = e?.response?.data?.detail || e?.message || String(e)
  } finally {
    tableInfoLoading.value = false
  }
}

async function runCompact() {
  if (!props.id) return
  confirmCompact.value = false
  compactError.value = ''
  compactResult.value = null
  compacting.value = true
  try {
    compactResult.value = await metaApi.compactTable(props.id)
    // Refresh the size figures so the dialog reflects the post-compaction state
    tableInfo.value = await metaApi.tableInfo(props.id)
  } catch (e: any) {
    compactError.value = e?.response?.data?.detail || e?.message || String(e)
  } finally {
    compacting.value = false
  }
}

const compactLabel = computed(() =>
  tableInfo.value?.reclaim_scope === 'database'
    ? t('Стиснути базу даних (VACUUM)')
    : t('Оптимізувати таблицю'),
)

function copyTableName() {
  if (!tableInfo.value) return
  navigator.clipboard.writeText(tableInfo.value.table_name)
  tableNameCopied.value = true
  setTimeout(() => { tableNameCopied.value = false }, 1500)
}

function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return '—'
  if (bytes < 1024) return `${bytes} Б`
  const units = ['КБ', 'МБ', 'ГБ', 'ТБ']
  let value = bytes / 1024
  let i = 0
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024
    i++
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[i]}`
}

type IconMap = Record<string, Component>
const lucideIcons = shallowRef<IconMap>({})
let iconsLoaded = false

function loadIcons() {
  if (iconsLoaded) return
  iconsLoaded = true
  import('@lucide/vue').then((lib) => { lucideIcons.value = lib as unknown as IconMap })
}

function getIconComponent(name?: string | null): Component | null {
  loadIcons()
  const raw = String(name ?? '').trim()
  if (!raw) return null
  const pascal = raw.split('-').map((s) => s.charAt(0).toUpperCase() + s.slice(1)).join('')
  return (lucideIcons.value[pascal] ?? null) as Component | null
}

// Client scripts set `severity` as a free-form string; trust it as a Button variant.
function scriptButtonVariant(severity?: string): ButtonVariants['variant'] {
  return (severity as ButtonVariants['variant']) || 'outline'
}

async function createShare() {
  if (!props.id || !props.doctype) return
  shareLoading.value = true
  try {
    const resp = await fetch('/api/v1/method/grunt.api.v1.share.create_share', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${auth.token}`,
      },
      body: JSON.stringify({
        doctype_name: props.doctype,
        doc_id: props.id,
        expires_at: shareExpires.value || null,
      }),
    })
    const json = await resp.json()
    if (json?.data?.token) {
      const shareHref = router.resolve({ name: 'document-share', params: { token: json.data.token } }).href
      shareLink.value = `${window.location.origin}${shareHref}`
    }
  } finally {
    shareLoading.value = false
  }
}

function copyShareLink() {
  if (shareLink.value) {
    navigator.clipboard.writeText(shareLink.value)
  }
}

async function handleRename() {
  if (!newDocId.value || newDocId.value === props.id) return
  isRenaming.value = true
  try {
    emit('rename', newDocId.value)
    showRenameDialog.value = false
  } finally {
    isRenaming.value = false
  }
}

function handleRefresh() {
  if (props.id) {
    queryClient.invalidateQueries({ queryKey: ['document', props.doctype, props.id] })
    emit('invalidate')
  }
}

function handleUndo() {
  router.go(0)
}

function toSplitButtonItem(btn: ScriptButton) {
  return {
    label: btn.label,
    icon: btn.icon,
    command: () => btn.action(),
  }
}

const ungroupedScriptButtons = computed(() =>
  (props.scriptButtons ?? []).filter((b) => !String(b.group ?? '').trim())
)

const groupedScriptButtons = computed(() => {
  const groups = new Map<string, ScriptButton[]>()
  for (const btn of props.scriptButtons ?? []) {
    const group = String(btn.group ?? '').trim()
    if (!group) continue
    if (!groups.has(group)) groups.set(group, [])
    groups.get(group)!.push(btn)
  }
  return Array.from(groups.entries()).map(([name, items]) => {
    const [primary, ...secondary] = items
    return {
      name,
      primary,
      secondary,
      model: secondary.map(toSplitButtonItem),
    }
  }).filter((g) => !!g.primary)
})

function menuItemIcon(item: any): Component | null {
  if (!item?.icon) return null
  if (typeof item.icon === 'string') return getIconComponent(item.icon)
  return item.icon as Component
}

const statusBadge = computed(() => resolveStatusBadge(props.dt, props.document))

const menuItems = computed(() => {
  const items: any[] = []

  for (const item of props.scriptMenuItems ?? []) {
    if (item.separator_before) items.push({ separator: true })
    items.push({
      label: item.label,
      icon: item.icon,
      command: () => item.action(),
    })
  }

  if (isDocTypeEditor.value) {
    items.push({ separator: true })
    items.push({
      label: t('Інформація про таблицю'),
      icon: Database,
      command: openTableInfo,
    })
  }

  if (props.id) {
    items.push({ separator: true })
    items.push({
      label: t('Duplicate'),
      icon: Copy,
      command: () => emit('duplicate'),
    })

    if (props.isDirty) {
      items.push({
        label: t('Discard changes'),
        icon: Undo,
        command: handleUndo,
      })
    }

    items.push({
      label: t('Activity log'),
      icon: History,
      command: () => emit('toggleLog'),
    })

    items.push({
      label: t('Share link'),
      icon: Share2,
      command: () => {
        showShareDialog.value = true
        shareLink.value = null
        shareExpires.value = ''
      },
    })
  }

  if (props.id) {
    items.push({ separator: true })
    items.push({
      label: t('Rename'),
      icon: Pencil,
      command: () => {
        newDocId.value = props.id || ''
        showRenameDialog.value = true
      },
    })

    items.push({
      label: t('Delete'),
      icon: Trash2,
      class: 'text-destructive',
      command: () => emit('delete'),
    })
  }

  return items
})
</script>

<template>
  <div class="sticky top-0 z-30 bg-background/95 backdrop-blur-sm border-b border-border/60 transition-all duration-300">
    <!-- Single row: breadcrumb (with document title as the last crumb) + primary actions -->
    <div class="flex items-center justify-between gap-3 px-4 py-2.5">
      <div class="flex items-center gap-2 min-w-0 flex-1">
        <AppBreadcrumb
          :workspace-name="workspace ?? 'grunt'"
          :doctype="doctype"
          :doc-id="id"
          :doc-label="docTitle"
          class="mb-0! min-w-0 flex-1"
        />
        <Badge v-if="statusBadge && hidePanelToggle" :variant="statusBadge.variant" class="animate-in fade-in slide-in-from-left-2 duration-300 text-xs h-5 px-1.5 shrink-0">
          {{ statusBadge.label }}
        </Badge>
        <Badge v-if="isDirty" variant="secondary" class="animate-in fade-in slide-in-from-left-2 duration-300 text-xs h-5 px-1.5 shrink-0">
          {{ t('Unsaved') }}
        </Badge>
      </div>
      <div class="flex items-center gap-2 shrink-0">
        <!-- Client script buttons -->
        <Button
          v-for="btn in ungroupedScriptButtons"
          :key="`script-${btn.label}`"
          size="sm"
          :variant="scriptButtonVariant(btn.severity)"
          @click="btn.action"
          :class="['hidden sm:inline-flex gap-1.5', btn.className]"
        >
          <component
            :is="getIconComponent(btn.icon)"
            v-if="btn.icon"
            class="size-3.5"
          />
          {{ btn.label }}
        </Button>

        <template v-for="grp in groupedScriptButtons" :key="`script-group-${grp.name}`">
          <Button
            v-if="grp.secondary.length === 0"
            size="sm"
            :variant="scriptButtonVariant(grp.primary.severity)"
            @click="grp.primary.action"
            :class="['hidden sm:inline-flex gap-1.5', grp.primary.className]"
            :title="grp.name"
          >
            <component
              :is="getIconComponent(grp.primary.icon)"
              v-if="grp.primary.icon"
              class="size-3.5"
            />
            {{ grp.primary.label }}
          </Button>
          <div v-else class="hidden sm:inline-flex" :class="grp.primary.className">
            <Button
              size="sm"
              :variant="scriptButtonVariant(grp.primary.severity)"
              class="rounded-r-none"
              :aria-label="grp.primary.label"
              :title="grp.name"
              @click="grp.primary.action"
            >
              <component
                :is="getIconComponent(grp.primary.icon)"
                v-if="grp.primary.icon"
                class="size-3.5"
              />
              {{ grp.primary.label }}
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger as-child>
                <Button size="sm" :variant="scriptButtonVariant(grp.primary.severity)" class="rounded-l-none border-l-0 px-2" :aria-label="`${grp.name} options`">
                  <ChevronDown class="size-3.5" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem v-for="item in grp.model" :key="item.label" @click="item.command">
                  <component
                    :is="getIconComponent(item.icon)"
                    v-if="item.icon"
                    class="size-3.5"
                  />
                  {{ item.label }}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </template>

        <Button variant="outline" v-if="id" class="text-foreground" :title="t('Refresh')" :disabled="isDirty || isLoading" @click="handleRefresh">
          <RefreshCw class="size-4" :class="{ 'animate-spin': isLoading }" />
        </Button>

        <Button
          v-if="id && !hidePanelToggle"
          variant="outline"
          class="text-foreground"
          :class="{ 'bg-muted': !panelOpen }"
          :title="`${panelOpen ? 'Сховати' : 'Показати'} деталі (Ctrl+])`"
          @click="togglePanel"
        >
          <PanelRight class="size-4" />
        </Button>

        <Button :disabled="isSaving" size="sm" @click="emit('save')" :title="`${t('Save')} (Ctrl+S)`">
          <Loader2 v-if="isSaving" class="size-4 animate-spin mr-1.5" />
          {{ t('Save') }}
        </Button>

        <!-- Context menu -->
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <Button variant="ghost" class="text-foreground hover:bg-muted/80 h-9 w-9 p-0">
                <EllipsisVertical class="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent class="w-56" align="end">
            <template v-for="(item, idx) in menuItems" :key="idx">
              <DropdownMenuSeparator v-if="item.separator" />
              <DropdownMenuItem v-else-if="item.url" as-child>
                <a :href="item.url" :target="item.target" class="flex items-center gap-2">
                  <component v-if="menuItemIcon(item)" :is="menuItemIcon(item)" class="size-4" />
                  <span>{{ item.label }}</span>
                </a>
              </DropdownMenuItem>
              <DropdownMenuItem v-else :variant="item.class === 'text-destructive' ? 'destructive' : 'default'" @click="item.command?.()">
                <component v-if="menuItemIcon(item)" :is="menuItemIcon(item)" class="size-4" />
                <span>{{ item.label }}</span>
              </DropdownMenuItem>
            </template>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>

    <!-- Workflow (inside the header card) -->
    <WorkflowBar v-if="!isLoading && dt && id && document && dt.workflow_state_field" :doctype="dt" :doc-id="id"
      :doc="document as Record<string, unknown>"
      @transitioned="handleRefresh" />
  </div>

  <!-- Share Dialog -->
  <Dialog :open="showShareDialog" @update:open="(v: boolean) => showShareDialog = v">
    <DialogContent class="max-w-md">
      <DialogHeader>
        <div class="flex items-center gap-2">
          <div class="size-9 rounded-lg bg-primary/10 flex items-center justify-center">
            <Share2 class="size-4.5 text-primary" />
          </div>
          <div>
            <DialogTitle class="text-base font-semibold">{{ t('Share link') }}</DialogTitle>
            <p class="text-muted-foreground">{{ t('Anyone with the link can view this document') }}</p>
          </div>
        </div>
      </DialogHeader>

      <template v-if="!shareLink">
        <div>
          <label class="font-medium text-muted-foreground block mb-1.5">{{ t('Expires at') }} ({{ t('optional') }})</label>
          <input
            v-model="shareExpires"
            type="datetime-local"
            class="w-full h-9 px-3 rounded-md border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" size="sm" @click="showShareDialog = false">{{ t('Cancel') }}</Button>
          <Button size="sm" :disabled="shareLoading" @click="createShare">
            <Loader2 v-if="shareLoading" class="size-3.5 mr-1.5 animate-spin" />
            {{ t('Generate link') }}
          </Button>
        </DialogFooter>
      </template>

      <template v-else>
        <div class="flex gap-2">
          <input
            :value="shareLink"
            readonly
            class="flex-1 h-9 px-3 rounded-md border border-border bg-muted font-mono focus:outline-none"
          />
          <Button variant="outline" size="sm" @click="copyShareLink" class="shrink-0">
            <CopyIcon class="size-3.5" />
          </Button>
        </div>
        <p class="text-muted-foreground">
          {{ t('Link copied to clipboard when you click the copy button.') }}
          <a :href="router.resolve({ name: 'workspace-list', params: { workspaceName: props.workspace ?? 'grunt', doctype: 'DocumentShare' } }).href" target="_blank" class="text-primary hover:underline ml-1">{{ t('Manage shares') }} →</a>
        </p>
        <DialogFooter>
          <Button variant="outline" size="sm" @click="shareLink = null; shareExpires = ''">{{ t('New link') }}</Button>
          <Button size="sm" @click="showShareDialog = false">{{ t('Done') }}</Button>
        </DialogFooter>
      </template>
    </DialogContent>
  </Dialog>

  <!-- Rename Dialog -->
  <Dialog :open="showRenameDialog" @update:open="(v: boolean) => showRenameDialog = v">
    <DialogContent class="max-w-md">
      <DialogHeader>
        <DialogTitle class="text-lg font-semibold">{{ t('Rename document') }}</DialogTitle>
      </DialogHeader>
      <div>
        <label class="font-medium text-muted-foreground block mb-1.5">{{ t('New ID') }}</label>
        <input
          v-model="newDocId"
          class="w-full h-10 px-3 rounded-md border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
          @keyup.enter="handleRename"
        />
      </div>
      <DialogFooter>
        <Button variant="outline" size="sm" @click="showRenameDialog = false">{{ t('Cancel') }}</Button>
        <Button size="sm" :disabled="isRenaming || !newDocId || newDocId === props.id" @click="handleRename">
          <Loader2 v-if="isRenaming" class="size-3.5 mr-1.5 animate-spin" />
          {{ t('Rename') }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <!-- Table Info Dialog (DocType editor) -->
  <Dialog :open="showTableInfoDialog" @update:open="(v: boolean) => showTableInfoDialog = v">
    <DialogContent class="max-w-md">
      <DialogHeader>
        <div class="flex items-center gap-2">
          <div class="size-9 rounded-lg bg-primary/10 flex items-center justify-center">
            <Database class="size-4.5 text-primary" />
          </div>
          <div>
            <DialogTitle class="text-base font-semibold">{{ t('Інформація про таблицю') }}</DialogTitle>
            <p class="text-muted-foreground">{{ t('Фізичне сховище цього типу документа') }}</p>
          </div>
        </div>
      </DialogHeader>

      <div v-if="tableInfoLoading" class="flex justify-center py-8">
        <Loader2 class="size-6 animate-spin text-muted-foreground" />
      </div>

      <p v-else-if="tableInfoError" class="text-destructive py-2">{{ tableInfoError }}</p>

      <div v-else-if="tableInfo">
        <dl class="divide-y divide-border">
          <div class="flex items-center justify-between gap-3 py-2">
            <dt class="text-muted-foreground shrink-0">{{ t('Назва таблиці') }}</dt>
            <dd class="flex items-center gap-1.5 min-w-0">
              <code class="font-mono truncate">{{ tableInfo.table_name }}</code>
              <Button variant="ghost" size="sm" class="size-6 p-0 shrink-0" :title="t('Copy')" @click="copyTableName">
                <CopyIcon class="size-3" />
              </Button>
            </dd>
          </div>
          <div class="flex items-center justify-between gap-3 py-2">
            <dt class="text-muted-foreground">{{ t('СКБД') }}</dt>
            <dd>{{ tableInfo.dialect }}</dd>
          </div>
          <div v-if="!tableInfo.exists" class="py-2 text-amber-600 dark:text-amber-400">
            {{ t('Таблиця ще не створена в базі даних') }}
          </div>
          <template v-else>
            <div class="flex items-center justify-between gap-3 py-2">
              <dt class="text-muted-foreground">{{ t('Рядків') }}</dt>
              <dd>{{ tableInfo.row_count?.toLocaleString() ?? '—' }}</dd>
            </div>
            <template v-if="tableInfo.size_supported">
              <div class="flex items-center justify-between gap-3 py-2">
                <dt class="text-muted-foreground">{{ t('Дані') }}</dt>
                <dd>{{ formatBytes(tableInfo.table_bytes) }}</dd>
              </div>
              <div class="flex items-center justify-between gap-3 py-2">
                <dt class="text-muted-foreground">{{ t('Індекси') }}</dt>
                <dd>{{ formatBytes(tableInfo.index_bytes) }}</dd>
              </div>
              <div class="flex items-center justify-between gap-3 py-2 font-medium">
                <dt>{{ t('Разом на диску') }}</dt>
                <dd>{{ formatBytes(tableInfo.total_bytes) }}</dd>
              </div>
              <div v-if="tableInfo.reclaimable_bytes" class="flex items-center justify-between gap-3 py-2">
                <dt class="text-muted-foreground">
                  {{ tableInfo.reclaim_scope === 'database' ? t('Вільно у файлі БД') : t('Можна вивільнити') }}
                </dt>
                <dd>{{ formatBytes(tableInfo.reclaimable_bytes) }}</dd>
              </div>
            </template>
            <div v-else class="py-2 text-muted-foreground">
              {{ t('Розмір недоступний для цієї бази даних') }}
            </div>
          </template>
        </dl>
        <p v-if="tableInfo.dead_tuples" class="mt-2 text-muted-foreground">
          {{ t('«мертвих» рядків: {n}').replace('{n}', String(tableInfo.dead_tuples)) }}
        </p>

        <!-- Compaction -->
        <div v-if="tableInfo.exists && tableInfo.size_supported" class="mt-3 border-t border-border pt-3">
          <div v-if="compacting" class="flex items-center gap-2 text-muted-foreground">
            <Loader2 class="size-3.5 animate-spin" />
            {{ t('Виконується стиснення… база може бути заблокована до завершення.') }}
          </div>

          <p v-else-if="compactError" class="text-destructive">{{ compactError }}</p>

          <div v-else-if="compactResult" class="flex items-start gap-2">
            <Check class="size-3.5 mt-0.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
            <span v-if="compactResult.freed_bytes && compactResult.freed_bytes > 0" class="text-foreground">
              {{ (compactResult.scope === 'database'
                    ? t('Звільнено {size} у файлі бази даних')
                    : t('Звільнено {size}')).replace('{size}', formatBytes(compactResult.freed_bytes)) }}
              <span class="text-muted-foreground">
                ({{ formatBytes(compactResult.before_bytes) }} → {{ formatBytes(compactResult.after_bytes) }})
              </span>
            </span>
            <span v-else class="text-muted-foreground">{{ t('Таблиця вже щільно упакована — вивільняти нічого.') }}</span>
          </div>

          <div v-else-if="confirmCompact">
            <p class="text-muted-foreground mb-2">
              <span v-if="tableInfo.reclaim_scope === 'database'">
                {{ t('VACUUM перепише весь файл бази даних і на час виконання заблокує запис. Продовжити?') }}
              </span>
              <span v-else>
                {{ t('Операція перепише таблицю під ексклюзивним блокуванням. Продовжити?') }}
              </span>
            </p>
            <div class="flex gap-2">
              <Button variant="outline" size="sm" @click="confirmCompact = false">{{ t('Cancel') }}</Button>
              <Button variant="destructive" size="sm" @click="runCompact">{{ t('Стиснути') }}</Button>
            </div>
          </div>

          <Button v-else variant="outline" size="sm" class="gap-1.5" @click="confirmCompact = true">
            <HardDriveDownload class="size-3.5" />
            {{ compactLabel }}
          </Button>
        </div>
      </div>

      <DialogFooter>
        <span v-if="tableNameCopied" class="text-muted-foreground self-center mr-auto">{{ t('Скопійовано') }}</span>
        <Button size="sm" :disabled="compacting" @click="showTableInfoDialog = false">{{ t('Done') }}</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
