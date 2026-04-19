<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useQueryClient } from '@tanstack/vue-query'
import type { DocType } from '@/types'
import {
  Loader2,
  EllipsisVertical,
  RefreshCw,
  Share2,
} from '@lucide/vue'
import WorkflowBar from '@/components/views/WorkflowBar.vue'

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
  scriptButtons: any[]
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'delete'): void
  (e: 'duplicate'): void
  (e: 'toggleLog'): void
  (e: 'invalidate'): void
}>()

const { t } = useI18n()
const auth = useAuthStore()
const router = useRouter()
const queryClient = useQueryClient()

const shareLink = ref<string | null>(null)
const shareLoading = ref(false)
const showShareDialog = ref(false)
const shareExpires = ref('')

async function createShare() {
  if (!props.id || !props.doctype) return
  shareLoading.value = true
  try {
    const resp = await fetch('/api/v1/share', {
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

function handleRefresh() {
  if (props.id) {
    queryClient.invalidateQueries({ queryKey: ['document', props.doctype, props.id] })
    emit('invalidate')
  }
}

function handleUndo() {
  router.go(0)
}

// PrimeVue Context Menu
const menu = ref()
const toggleMenu = (event: Event) => {
    menu.value.toggle(event)
}

const menuItems = computed(() => {
    const items: any[] = []

    if (props.id) {
        items.push({
            label: t('Print'),
            icon: 'pi pi-print',
            items: [
                {
                    label: 'Excel (.xlsx)',
                    icon: 'pi pi-file-excel',
                    url: `/api/v1/docs/${props.doctype}/${props.id}/print?fmt=xlsx&token=${auth.token}`,
                    target: '_self'
                },
                {
                    label: 'PDF',
                    icon: 'pi pi-file-pdf',
                    url: `/api/v1/docs/${props.doctype}/${props.id}/print?fmt=pdf&token=${auth.token}`,
                    target: '_self'
                },
                {
                    label: 'HTML',
                    icon: 'pi pi-globe',
                    url: `/api/v1/docs/${props.doctype}/${props.id}/print?fmt=html&token=${auth.token}`,
                    target: '_blank'
                }
            ]
        })

        items.push({
            label: t('Open in new tab'),
            icon: 'pi pi-external-link',
            url: `/${props.workspace ?? ''}/list/${props.doctype}/${props.id}`,
            target: '_blank'
        })
    }

    items.push({
        label: t('Edit DocType'),
        icon: 'pi pi-cog',
        url: `/${props.workspace ?? ''}/list/DocType/${props.doctype}`,
        target: '_blank'
    })

    if (props.dt) {
        items.push({
            label: t('Configure print'),
            icon: 'pi pi-sliders-h',
            url: `/${props.workspace ?? 'grunt'}/list/PrintFormat?filter[doctype]=${props.doctype}`,
            target: '_blank'
        })
    }

    items.push({ separator: true })

    if (props.id) {
        items.push({
            label: t('Duplicate'),
            icon: 'pi pi-copy',
            command: () => emit('duplicate')
        })

        if (props.isDirty) {
            items.push({
                label: t('Discard changes'),
                icon: 'pi pi-undo',
                command: handleUndo
            })
        }

        items.push({
            label: t('Activity log'),
            icon: 'pi pi-history',
            command: () => emit('toggleLog')
        })

        items.push({
            label: t('Share link'),
            icon: 'pi pi-share-alt',
            command: () => {
                showShareDialog.value = true
                shareLink.value = null
                shareExpires.value = ''
            }
        })
    }

    if (props.id) {
        items.push({ separator: true })
        items.push({
            label: t('Delete'),
            icon: 'pi pi-trash',
            class: 'text-destructive',
            command: () => emit('delete')
        })
    }

    return items
})
</script>

<template>
  <div class="bg-card border-b border-border/60 mb-4 transition-all duration-300">
    <!-- Top bar: actions -->
    <div class="flex items-center justify-between gap-4 px-4 py-2.5">
      <div class="min-w-0 flex items-center gap-3">
        <h1 class="text-xl font-bold text-foreground truncate selection:bg-primary/20">{{ docTitle }}</h1>
        <Badge v-if="isDirty" severity="contrast" class="animate-in fade-in slide-in-from-left-2 duration-300 text-[10px] h-5 px-1.5 border-yellow-500/30 bg-yellow-500/10 text-yellow-700 dark:text-amber-400">
          {{ t('Unsaved') }}
        </Badge>
      </div>
      <div class="flex items-center gap-2 shrink-0">
        <!-- Client script buttons -->
        <Button v-for="btn in scriptButtons" :key="btn.label" outlined size="small"
          :severity="btn.severity" @click="btn.action" class="hidden sm:inline-flex">
          {{ btn.label }}
        </Button>

        <Button v-if="id" outlined class="text-foreground" :title="t('Refresh')"
          :disabled="isDirty || isLoading"
          @click="handleRefresh">
          <RefreshCw class="size-4" :class="{ 'animate-spin': isLoading }" />
        </Button>

        <Button :disabled="isSaving" size="small" @click="emit('save')" class="shadow-sm hover:shadow-md transition-shadow" :title="`${t('Save')} (Ctrl+S)`">
          <Loader2 v-if="isSaving" class="size-4 animate-spin mr-1.5" />
          {{ t('Save') }}
        </Button>

        <!-- Context menu -->
        <Button text class="text-foreground hover:bg-muted/80 h-9 w-9 p-0" @click="toggleMenu">
            <EllipsisVertical class="size-4" />
        </Button>
        <Menu ref="menu" :model="menuItems" :popup="true" class="w-56" />
      </div>
    </div>

    <!-- Workflow (inside the header card) -->
    <WorkflowBar v-if="!isLoading && dt && id && document && dt.workflow" :doctype="dt" :doc-id="id"
      :doc="document as Record<string, unknown>"
      @transitioned="handleRefresh" />
  </div>

  <!-- Share Dialog -->
  <Teleport to="body">
    <div v-if="showShareDialog" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="fixed inset-0 bg-black/40" @click="showShareDialog = false" />
      <div class="relative bg-card border border-border rounded-xl shadow-2xl w-full max-w-md mx-4 p-6 overflow-hidden">
        <div class="flex items-center gap-2 mb-5">
          <div class="size-9 rounded-lg bg-primary/10 flex items-center justify-center">
            <Share2 class="size-4.5 text-primary" />
          </div>
          <div>
            <h2 class="text-base font-semibold">{{ t('Share link') }}</h2>
            <p class="text-xs text-muted-foreground">{{ t('Anyone with the link can view this document') }}</p>
          </div>
        </div>

        <template v-if="!shareLink">
          <div class="mb-4">
            <label class="text-xs font-medium text-muted-foreground block mb-1.5">{{ t('Expires at') }} ({{ t('optional') }})</label>
            <input
              v-model="shareExpires"
              type="datetime-local"
              class="w-full h-9 px-3 text-sm rounded-md border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
          </div>
          <div class="flex justify-end gap-2">
            <Button outlined size="small" @click="showShareDialog = false">{{ t('Cancel') }}</Button>
            <Button size="small" :disabled="shareLoading" @click="createShare">
              <Loader2 v-if="shareLoading" class="size-3.5 mr-1.5 animate-spin" />
              {{ t('Generate link') }}
            </Button>
          </div>
        </template>

        <template v-else>
          <div class="flex gap-2 mb-4">
            <input
              :value="shareLink"
              readonly
              class="flex-1 h-9 px-3 text-xs rounded-md border border-border bg-muted font-mono focus:outline-none"
            />
            <Button outlined size="small" @click="copyShareLink" class="shrink-0">
              <Copy class="size-3.5" />
            </Button>
          </div>
          <p class="text-xs text-muted-foreground mb-4">
            {{ t('Link copied to clipboard when you click the copy button.') }}
            <a :href="`/${props.workspace ?? 'grunt'}/list/DocumentShare`" target="_blank" class="text-primary hover:underline ml-1">{{ t('Manage shares') }} →</a>
          </p>
          <div class="flex justify-end gap-2">
            <Button outlined size="small" @click="shareLink = null; shareExpires = ''">{{ t('New link') }}</Button>
            <Button size="small" @click="showShareDialog = false">{{ t('Done') }}</Button>
          </div>
        </template>
      </div>
    </div>
  </Teleport>
</template>
