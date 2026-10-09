<script setup lang="ts">
import { formatNumber } from '@/core/currency'
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import type { DocType } from '@/types'
import type { ActionRegistry } from '@/core/actions'
import type { FormProxy } from '@/core/scripting/executor'
import ActionButtons from '@/components/views/actions/ActionButtons.vue'
import ActionMenu from '@/components/views/actions/ActionMenu.vue'
import {
  Loader2,
  Share2,
  Copy as CopyIcon,
  Database,
  Check,
  HardDriveDownload,
} from '@lucide/vue'
import { metaApi, type DocTypeTableInfo, type DocTypeCompactResult } from '@/core/api/meta'
import { useDocPanel } from '@/components/views/sidebar/useDocPanel'
import AppBreadcrumb from '@/components/app/AppBreadcrumb.vue'
import { resolveStatusBadge } from '@/core/status'
import DocLinksDialog from './DocLinksDialog.vue'
import WorkflowActions, { type WorkflowUi } from '@/components/views/WorkflowActions.vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { docUrl } from '@/core/workspaceUrl'
const props = defineProps<{
  dt: DocType | null
  doctype: string
  id: string | null
  workspace?: string
  docTitle: string
  document: any
  /** The form's buttons & menu (core/actions.ts), filled by global_form.js and scripts. */
  actions: ActionRegistry<FormProxy>
  /** Workflow state & the transition awaiting its prompt fields (useFormController). */
  workflow: WorkflowUi
  isDirty: boolean
  isLoading: boolean
  hidePanelToggle?: boolean
}>()

// Dialogs the standard actions open (frm.share() / frm.rename() / frm.show_links()).
const showShareDialog = defineModel<boolean>('shareOpen', { default: false })
const showRenameDialog = defineModel<boolean>('renameOpen', { default: false })
const showLinksDialog = defineModel<boolean>('linksOpen', { default: false })

const emit = defineEmits<{
  (e: 'rename', newId: string): void
}>()

const { t } = useI18n()
const auth = useAuthStore()
const { open: panelOpen, toggle: togglePanel } = useDocPanel()

const shareLink = ref<string | null>(null)
const shareLoading = ref(false)
const shareExpires = ref('')
const newDocId = ref('')

// Fresh state every time a dialog opens.
watch(showShareDialog, (open) => {
  if (open) {
    shareLink.value = null
    shareExpires.value = ''
  }
})
watch(showRenameDialog, (open) => {
  if (open) newDocId.value = props.id || ''
})

const toolbarActions = props.actions.resolved('toolbar')
const primaryActions = props.actions.resolved('primary')
const menuActions = props.actions.resolved('menu')
const isRenaming = ref(false)

// Details sidebar toggle - first in the «⋯» menu. Its shortcut (Mod+]) runs it
// through the action registry; useDocPanel keeps a fallback for other pages.
props.actions.add({
  id: 'toggle_details',
  label: () => (panelOpen.value ? 'Hide details' : 'Show details'),
  icon: 'panel-right',
  placement: 'menu',
  group: 'view',
  order: 10,
  shortcut: 'Mod+]',
  visible: () => !props.hidePanelToggle,
  action: () => togglePanel(),
})

// Table info (DocType editor only) - registered like any other action.
props.actions.add({
  id: 'table_info',
  label: 'Table info',
  icon: 'database',
  placement: 'menu',
  group: 'doctype',
  order: 150,
  visible: () => props.doctype === 'DocType' && !!props.id,
  action: () => openTableInfo(),
})
const showTableInfoDialog = ref(false)
const tableInfo = ref<DocTypeTableInfo | null>(null)
const tableInfoLoading = ref(false)
const tableInfoError = ref('')
const tableNameCopied = ref(false)

// Compaction (VACUUM / OPTIMIZE) - blocking, so it goes through a confirm step
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
    ? t('Compact database (VACUUM)')
    : t('Optimize table'),
)

function copyTableName() {
  if (!tableInfo.value) return
  navigator.clipboard.writeText(tableInfo.value.table_name)
  tableNameCopied.value = true
  setTimeout(() => { tableNameCopied.value = false }, 1500)
}

function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return '—'
  if (bytes < 1024) return `${bytes} ${t('B')}`
  const units = [t('KB'), t('MB'), t('GB'), t('TB')]
  let value = bytes / 1024
  let i = 0
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024
    i++
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[i]}`
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
      // /share/:token is a server-rendered website page (grunt/website/www/share/),
      // not an SPA route - build the URL directly.
      shareLink.value = `${window.location.origin}/share/${json.data.token}`
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


const statusBadge = computed(() => resolveStatusBadge(props.dt, props.document))
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
          :is-new="id === null"
          class="mb-0! min-w-0 flex-1"
        />
        <Badge v-if="statusBadge && (hidePanelToggle || !panelOpen)" variant="outline" :class="['animate-in fade-in slide-in-from-left-2 duration-300', statusBadge.class]">
          {{ statusBadge.label }}
        </Badge>
        <Badge v-if="isDirty" variant="secondary" class="animate-in fade-in slide-in-from-left-2 duration-300 text-xs h-5 px-1.5 shrink-0">
          {{ t('Unsaved') }}
        </Badge>
      </div>
      <div class="flex items-center gap-2 shrink-0">
        <!-- Actions: global_form.js + the DocType's script + ClientScripts (core/actions.ts) -->
        <ActionButtons :toolbar="toolbarActions" compact />


        <!-- Workflow transitions - next to Save; the state is in the sidebar -->
        <WorkflowActions v-if="!isLoading && dt && id && document && dt.workflow_state_field" :doctype="dt"
          :doc="document as Record<string, unknown>" :actions="actions" :workflow="workflow" />

        <ActionButtons :toolbar="[]" :primary="primaryActions" />
        <ActionMenu :actions="menuActions" trigger-variant="ghost" />
      </div>
    </div>
  </div>

  <DocLinksDialog v-if="id" v-model:open="showLinksDialog" :doctype="doctype" :doc-id="id" :workspace="workspace" />

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
          <a :href="docUrl('DocumentShare', null, props.workspace)" target="_blank" class="text-primary hover:underline ml-1">{{ t('Manage shares') }} →</a>
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
            <DialogTitle class="text-base font-semibold">{{ t('Table info') }}</DialogTitle>
            <p class="text-muted-foreground">{{ t('Physical storage of this document type') }}</p>
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
            <dt class="text-muted-foreground shrink-0">{{ t('Table name') }}</dt>
            <dd class="flex items-center gap-1.5 min-w-0">
              <code class="font-mono truncate">{{ tableInfo.table_name }}</code>
              <Button variant="ghost" size="sm" class="size-6 p-0 shrink-0" :title="t('Copy')" @click="copyTableName">
                <CopyIcon class="size-3" />
              </Button>
            </dd>
          </div>
          <div class="flex items-center justify-between gap-3 py-2">
            <dt class="text-muted-foreground">{{ t('DBMS') }}</dt>
            <dd>{{ tableInfo.dialect }}</dd>
          </div>
          <div v-if="!tableInfo.exists" class="py-2 text-amber-600 dark:text-amber-400">
            {{ t('The table has not been created in the database yet') }}
          </div>
          <template v-else>
            <div class="flex items-center justify-between gap-3 py-2">
              <dt class="text-muted-foreground">{{ t('Rows') }}</dt>
              <dd>{{ tableInfo.row_count != null ? formatNumber(tableInfo.row_count) : '—' }}</dd>
            </div>
            <template v-if="tableInfo.size_supported">
              <div class="flex items-center justify-between gap-3 py-2">
                <dt class="text-muted-foreground">{{ t('Data') }}</dt>
                <dd>{{ formatBytes(tableInfo.table_bytes) }}</dd>
              </div>
              <div class="flex items-center justify-between gap-3 py-2">
                <dt class="text-muted-foreground">{{ t('Indexes') }}</dt>
                <dd>{{ formatBytes(tableInfo.index_bytes) }}</dd>
              </div>
              <div class="flex items-center justify-between gap-3 py-2 font-medium">
                <dt>{{ t('Total on disk') }}</dt>
                <dd>{{ formatBytes(tableInfo.total_bytes) }}</dd>
              </div>
              <div v-if="tableInfo.reclaimable_bytes" class="flex items-center justify-between gap-3 py-2">
                <dt class="text-muted-foreground">
                  {{ tableInfo.reclaim_scope === 'database' ? t('Free in the database file') : t('Reclaimable') }}
                </dt>
                <dd>{{ formatBytes(tableInfo.reclaimable_bytes) }}</dd>
              </div>
            </template>
            <div v-else class="py-2 text-muted-foreground">
              {{ t('Size is not available for this database') }}
            </div>
          </template>
        </dl>
        <p v-if="tableInfo.dead_tuples" class="mt-2 text-muted-foreground">
          {{ t('Dead rows: {n}', { n: String(tableInfo.dead_tuples) }) }}
        </p>

        <!-- Compaction -->
        <div v-if="tableInfo.exists && tableInfo.size_supported" class="mt-3 border-t border-border pt-3">
          <div v-if="compacting" class="flex items-center gap-2 text-muted-foreground">
            <Loader2 class="size-3.5 animate-spin" />
            {{ t('Compacting… the database may be locked until it finishes.') }}
          </div>

          <p v-else-if="compactError" class="text-destructive">{{ compactError }}</p>

          <div v-else-if="compactResult" class="flex items-start gap-2">
            <Check class="size-3.5 mt-0.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
            <span v-if="compactResult.freed_bytes && compactResult.freed_bytes > 0" class="text-foreground">
              {{ compactResult.scope === 'database'
                    ? t('Freed {size} in the database file', { size: formatBytes(compactResult.freed_bytes) })
                    : t('Freed {size}', { size: formatBytes(compactResult.freed_bytes) }) }}
              <span class="text-muted-foreground">
                ({{ formatBytes(compactResult.before_bytes) }} → {{ formatBytes(compactResult.after_bytes) }})
              </span>
            </span>
            <span v-else class="text-muted-foreground">{{ t('The table is already compact — nothing to reclaim.') }}</span>
          </div>

          <div v-else-if="confirmCompact">
            <p class="text-muted-foreground mb-2">
              <span v-if="tableInfo.reclaim_scope === 'database'">
                {{ t('VACUUM rewrites the whole database file and blocks writes while it runs. Continue?') }}
              </span>
              <span v-else>
                {{ t('This rewrites the table under an exclusive lock. Continue?') }}
              </span>
            </p>
            <div class="flex gap-2">
              <Button variant="outline" size="sm" @click="confirmCompact = false">{{ t('Cancel') }}</Button>
              <Button variant="destructive" size="sm" @click="runCompact">{{ t('Compact') }}</Button>
            </div>
          </div>

          <Button v-else variant="outline" size="sm" class="gap-1.5" @click="confirmCompact = true">
            <HardDriveDownload class="size-3.5" />
            {{ compactLabel }}
          </Button>
        </div>
      </div>

      <DialogFooter>
        <span v-if="tableNameCopied" class="text-muted-foreground self-center mr-auto">{{ t('Copied') }}</span>
        <Button size="sm" :disabled="compacting" @click="showTableInfoDialog = false">{{ t('Done') }}</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
