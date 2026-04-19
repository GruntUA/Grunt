<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useQueryClient } from '@tanstack/vue-query'
import type { DocType } from '@/types'
import Button from 'primevue/button'
import Badge from 'primevue/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Loader2,
  Printer,
  FileSpreadsheet,
  FileText,
  Globe,
  Trash2,
  History,
  Copy,
  Undo2,
  EllipsisVertical,
  ExternalLink,
  Settings2,
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
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <Button text class="text-foreground hover:bg-muted/80">
              <EllipsisVertical class="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" class="w-52 p-1.5 selection:bg-primary/10">
            <!-- Print submenu -->
            <DropdownMenuSub v-if="id">
              <DropdownMenuSubTrigger class="gap-2" :title="`${t('Print')} (Ctrl+P)`">
                <Printer class="size-4 text-muted-foreground" />
                <span>{{ t('Print') }}</span>
              </DropdownMenuSubTrigger>
              <DropdownMenuSubContent class="p-1.5">
                <DropdownMenuItem as="a" :href="`/api/v1/docs/${doctype}/${id}/print?fmt=xlsx&token=${auth.token}`" class="gap-2">
                  <FileSpreadsheet class="size-4 text-emerald-500" />
                  <span>Excel (.xlsx)</span>
                </DropdownMenuItem>
                <DropdownMenuItem as="a" :href="`/api/v1/docs/${doctype}/${id}/print?fmt=pdf&token=${auth.token}`" class="gap-2">
                  <FileText class="size-4 text-rose-500" />
                  <span>PDF</span>
                </DropdownMenuItem>
                <DropdownMenuItem as="a" :href="`/api/v1/docs/${doctype}/${id}/print?fmt=html&token=${auth.token}`"
                  target="_blank" class="gap-2">
                  <Globe class="size-4 text-sky-500" />
                  <span>HTML</span>
                </DropdownMenuItem>
              </DropdownMenuSubContent>
            </DropdownMenuSub>

            <DropdownMenuItem v-if="id" as="a" :href="`/${props.workspace ?? ''}/list/${doctype}/${id}`"
              target="_blank" class="gap-2">
              <ExternalLink class="size-4 text-muted-foreground" />
              <span>{{ t('Open in new tab') }}</span>
            </DropdownMenuItem>

            <DropdownMenuItem as="a" :href="`/${props.workspace ?? ''}/list/DocType/${doctype}`" target="_blank" class="gap-2">
              <Settings2 class="size-4 text-muted-foreground" />
              <span>{{ t('Edit DocType') }}</span>
            </DropdownMenuItem>

            <DropdownMenuItem v-if="dt" as="a"
              :href="`/${props.workspace ?? 'grunt'}/list/PrintFormat?filter[doctype]=${doctype}`" target="_blank" class="gap-2">
              <Printer class="size-4 text-muted-foreground" />
              <span>{{ t('Configure print') }}</span>
            </DropdownMenuItem>

            <DropdownMenuSeparator />

            <DropdownMenuItem v-if="id" @click="emit('duplicate')" class="gap-2">
              <Copy class="size-4 text-muted-foreground" />
              <span>{{ t('Duplicate') }}</span>
            </DropdownMenuItem>

            <DropdownMenuItem v-if="id && isDirty" @click="handleUndo" class="gap-2">
              <Undo2 class="size-4 text-muted-foreground" />
              <span>{{ t('Discard changes') }}</span>
            </DropdownMenuItem>

            <DropdownMenuItem v-if="id" @click="emit('toggleLog')" class="gap-2">
              <History class="size-4 text-muted-foreground" />
              <span>{{ t('Activity log') }}</span>
            </DropdownMenuItem>

            <DropdownMenuItem v-if="id" @click="showShareDialog = true; shareLink = null; shareExpires = ''" class="gap-2">
              <Share2 class="size-4 text-muted-foreground" />
              <span>{{ t('Share link') }}</span>
            </DropdownMenuItem>

            <template v-if="id">
              <DropdownMenuSeparator />
              <DropdownMenuItem class="text-destructive focus:text-destructive focus:bg-destructive/10 gap-2" @click="emit('delete')">
                <Trash2 class="size-4" />
                <span>{{ t('Delete') }}</span>
              </DropdownMenuItem>
            </template>
          </DropdownMenuContent>
        </DropdownMenu>
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
      <div class="relative bg-card border border-border rounded-xl shadow-2xl w-full max-w-md mx-4 p-6">
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
