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
} from '@lucide/vue'
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
        <Badge v-if="isDirty" variant="warning" class="animate-in fade-in slide-in-from-left-2 duration-300 text-xs h-5 px-1.5 shrink-0">
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
            <p class="text-xs text-muted-foreground">{{ t('Anyone with the link can view this document') }}</p>
          </div>
        </div>
      </DialogHeader>

      <template v-if="!shareLink">
        <div>
          <label class="text-xs font-medium text-muted-foreground block mb-1.5">{{ t('Expires at') }} ({{ t('optional') }})</label>
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
            class="flex-1 h-9 px-3 text-xs rounded-md border border-border bg-muted font-mono focus:outline-none"
          />
          <Button variant="outline" size="sm" @click="copyShareLink" class="shrink-0">
            <CopyIcon class="size-3.5" />
          </Button>
        </div>
        <p class="text-xs text-muted-foreground">
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
        <label class="text-xs font-medium text-muted-foreground block mb-1.5">{{ t('New ID') }}</label>
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
</template>
