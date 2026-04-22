<script setup lang="ts">
import { ref, computed, onMounted, provide } from 'vue'
import { useRouter } from 'vue-router'
import { useDocTypeStore } from '@/stores/doctype'
import { useDocument } from '@/core/composables/useDocument'
import { useToast } from '@/core/composables/useToast'
import { useWebSocket } from '@/core/composables/useWebSocket'
import { usePresence } from '@/core/composables/usePresence'
import { useClientScripts } from '@/core/composables/useClientScripts'
import { useLinkCreate } from '@/core/composables/useLinkCreate'
import { useFormValidation } from '@/core/composables/useFormValidation'
import { useFormDocWatcher } from '@/core/composables/useFormDocWatcher'
import { useFormNavigation } from '@/core/composables/useFormNavigation'
import { useFormSave } from '@/core/composables/useFormSave'
import { useQueryClient } from '@tanstack/vue-query'
import { useShortcut } from '@/core/composables/useShortcuts'
import type { DocType, GruntDocument } from '@/types'
import { Spinner } from '@/components/ui/spinner'
import { History } from '@lucide/vue'

import FormRenderer from '@/core/renderer/FormRenderer.vue'
import DocSidebar from '@/components/views/DocSidebar.vue'
import VersionHistoryPanel from '@/components/views/VersionHistoryPanel.vue'
import QuickEntryDialog from '@/components/views/QuickEntryDialog.vue'

// Custom sub-components
import FormHeader from '@/components/views/form/FormHeader.vue'
import FormModals from '@/components/views/form/FormModals.vue'

const props = defineProps<{ doctype: string; id: string | null; workspace?: string }>()
const router = useRouter()
const dtStore = useDocTypeStore()
const toast = useToast()
const queryClient = useQueryClient()
const { startLinkCreate, finishLinkCreate, restoreLinkDraft } = useLinkCreate()

const dt = ref<DocType | null>(null)
const { document, form, isLoading, isDirty, isSaving, save, remove } = useDocument(props.doctype, props.id)

// ── WebSocket real-time + presence ───────────────────────────────────────────
const wsUrl = computed(() => props.id ? `/api/v1/ws/${props.doctype}/${props.id}` : null)
const docWs = useWebSocket(wsUrl)
const { lastMessage } = docWs
const { users: presenceUsers, fieldLocks, focusField, blurField } = usePresence(docWs)

// ── Validation + Save ─────────────────────────────────────────────────────────
let saveHandler: (() => Promise<void>) | null = null

// ── Client scripts ──────────────────────────────────────────────────────────
const {
  buttons: scriptButtons,
  displayOverrides,
  reqdOverrides,
  runEvent: runScriptEvent,
  getLinkFilters,
} = useClientScripts(props.doctype, {
  getDoc: () => form.value,
  getFields: () => (dt.value?.fields ?? []) as Record<string, unknown>[],
  isNew: () => !props.id,
  setValue: (field, value) => { form.value[field] = value },
  reload: async () => {
    if (props.id) {
      await queryClient.invalidateQueries({ queryKey: ['document', props.doctype, props.id] })
    }
  },
  save: async () => {
    if (saveHandler) {
      await saveHandler()
    }
  },
  lastMessage,
})

const {
  validationErrors,
  focusFirstError,
  validateForm,
} = useFormValidation({
  dt,
  form,
  displayOverrides,
  reqdOverrides,
  toast,
})

// Provide link filter resolver to all descendant Link fields via inject
provide('getLinkFilters', getLinkFilters)
// Provide document context so Attach/Image fields can set attached_to_* on upload
provide('docContext', { doctype: props.doctype, getId: () => props.id })

// ── Modals & Navigation ──────────────────────────────────────────────────────
const showDeleteModal = ref(false)

// Quick Entry Dialog state
const quickEntryDt = ref<import('@/types').DocType | null>(null)
const quickEntryPreset = ref<Record<string, unknown>>({})
const quickEntryFieldname = ref('')

const showVersions = ref(false)

const {
  showLeaveModal,
  markAllowLeave,
  confirmLeave,
  cancelLeave,
  goToList,
} = useFormNavigation({
  router,
  doctype: props.doctype,
  workspace: props.workspace,
  isDirty,
  showDeleteModal,
  showVersions,
  isQuickEntryOpen: computed(() => Boolean(quickEntryDt.value)),
})

useFormDocWatcher({
  lastMessage,
  isDirty,
  doctype: props.doctype,
  id: props.id,
  queryClient,
  toast,
})

const { handleSave } = useFormSave({
  doctype: props.doctype,
  id: props.id,
  workspace: props.workspace,
  dt,
  validationErrors,
  save,
  runScriptEvent,
  validateForm,
  focusFirstError,
  markAllowLeave,
  finishLinkCreate,
  queryClient,
  dtStore,
  router,
  toast,
})
saveHandler = handleSave

function onVersionRestored() {
  queryClient.invalidateQueries({ queryKey: ['document', props.doctype, props.id] })
  showVersions.value = false
}

onMounted(async () => {
  dt.value = await dtStore.get(props.doctype)

  // Apply duplicated document data from history state
  if (!props.id && window.history.state?.duplicate) {
    try {
      const clone = JSON.parse(window.history.state.duplicate) as Record<string, unknown>
      Object.assign(form.value, clone)
    } catch { /* ignore malformed state */ }
  }

  // Apply initial data from history state (e.g. from Calendar quick-add)
  if (!props.id && window.history.state?.initial_data) {
    try {
      const initial = JSON.parse(window.history.state.initial_data) as Record<string, unknown>
      Object.assign(form.value, initial)
    } catch { /* ignore malformed state */ }
  }

  // Restore draft + set link field after returning from a link-create flow
  const linkReturn = restoreLinkDraft(props.doctype, props.id, form.value)
  if (linkReturn) {
    form.value[linkReturn.fieldname] = linkReturn.value
    toast.info(`Поле встановлено: ${linkReturn.value}`)
  }

  await runScriptEvent('on_load')
})

// ── Shortcuts ────────────────────────────────────────────────────────────────
useShortcut(['ctrl+s', 'cmd+s'], () => {
  handleSave()
}, { preventDefault: true, allowInInput: true })

useShortcut(['ctrl+p', 'cmd+p'], () => {
  window.print()
}, { preventDefault: true, allowInInput: true })

/**
 * Handle "create-new" event from a Link field inside the form.
 * If the linked DocType has quick_entry enabled — show the Quick Entry dialog.
 * Otherwise save a draft and navigate to the full linked-doc form.
 */
async function handleCreateNew(linkedDoctype: string, preset: string, fieldname: string) {
  const linkedDt = await dtStore.get(linkedDoctype)
  if (linkedDt?.quick_entry) {
    quickEntryDt.value = linkedDt
    quickEntryPreset.value = preset ? { name: preset } : {}
    quickEntryFieldname.value = fieldname
    return
  }
  markAllowLeave()
  startLinkCreate(
    linkedDoctype,
    preset,
    fieldname,
    props.doctype,
    props.id,
    { ...form.value },
    props.workspace,
  )
}

/** Called after QuickEntryDialog saves — set the Link field value on the current form. */
function onQuickEntrySaved(docname: string) {
  if (quickEntryFieldname.value) {
    form.value[quickEntryFieldname.value] = docname
  }
  quickEntryDt.value = null
}

const docTitle = computed(() => {
  if (!document.value) return props.id ? '...' : `Новий ${dt.value?.label ?? ''}`
  const tf = dt.value?.title_field
  if (dt.value?.is_singleton && !tf) return dt.value.label
  return (tf && document.value[tf] as string) || document.value.name || `Новий ${dt.value?.label ?? ''}`
})

async function handleDelete() {
  try {
    await remove()
    toast.success('Видалено')
    queryClient.invalidateQueries({ queryKey: ['documents', props.doctype] })
    goToList()
  } catch {
    toast.error('Помилка видалення')
  }
  showDeleteModal.value = false
}

function handleDuplicate() {
  const clone = { ...form.value }
  const protectedFields = ['id', 'name', 'created_at', 'updated_at', 'owner', 'modified_by', 'workflow_state']
  protectedFields.forEach(f => delete clone[f])

  const path = props.workspace
    ? `/${props.workspace}/${props.doctype}/new`
    : `/${props.doctype}/new`

  markAllowLeave()
  router.push({ path, state: { duplicate: JSON.stringify(clone) } })
}

function onFormUpdate(updated: Record<string, unknown>) {
  const changedFields: string[] = []
  for (const key of Object.keys(updated)) {
    if (updated[key] !== form.value[key]) changedFields.push(key)
  }
  Object.assign(form.value, updated)
  for (const field of changedFields) runScriptEvent('on_change', field)
}
</script>

<template>
  <div class="flex flex-1 flex-col gap-5 p-4 sm:p-6 lg:p-8 animate-in fade-in duration-500">
    <!-- Header -->
    <FormHeader :dt="dt" :doctype="doctype" :id="id" :workspace="workspace" :doc-title="docTitle" :document="document"
      :is-dirty="isDirty" :is-loading="isLoading" :is-saving="isSaving" :script-buttons="scriptButtons"
      @save="handleSave" @delete="showDeleteModal = true" @duplicate="handleDuplicate"
      @invalidate="queryClient.invalidateQueries({ queryKey: ['document', props.doctype, props.id] })" />

    <!-- Loading -->
    <div v-if="isLoading || !dt" class="flex justify-center py-24">
      <Spinner size="lg" />
    </div>

    <template v-else>
      <div class="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-5">
        <!-- Left Column -->
        <div class="min-w-0 flex flex-col gap-4">
          <!-- Main Form Card -->
          <div class="bg-card border border-border rounded-md shadow-sm p-5">
            <FormRenderer :doctype="dt" :model-value="form" :disabled="isSaving" :errors="validationErrors"
              :overrides="displayOverrides" :reqd-overrides="reqdOverrides" :field-locks="fieldLocks"
              @update:model-value="onFormUpdate($event)" @field-focus="focusField($event)"
              @field-blur="blurField($event)" @create-new="handleCreateNew" />
          </div>


          <!-- Version history -->
          <div v-if="id && dt?.track_changes" class="form-section">
            <button type="button" class="form-section-header w-full hover:bg-muted/70 transition-colors"
              @click="showVersions = !showVersions">
              <History class="size-3.5 text-muted-foreground" />
              <span class="flex-1 text-left">Версії документа</span>
              <div class="size-4 flex items-center justify-center transition-transform duration-300"
                :class="{ 'rotate-180': showVersions }">
                <svg width="10" height="6" viewBox="0 0 10 6" fill="none" stroke="currentColor" stroke-width="2"
                  stroke-linecap="round" stroke-linejoin="round">
                  <path d="M1 1L5 5L9 1" />
                </svg>
              </div>
            </button>
            <div v-if="showVersions">
              <VersionHistoryPanel :doctype="doctype" :doc-id="id" @restored="onVersionRestored" />
            </div>
          </div>
        </div>

        <!-- Right Column: Sidebar -->
        <DocSidebar v-if="id && document" :doctype="dt" :document="document as GruntDocument" :workspace="workspace"
          :users="presenceUsers" class="lg:sticky lg:top-8 lg:self-start hidden lg:block" />
      </div>
    </template>

    <!-- Quick Entry Dialog (from Link field) -->
    <QuickEntryDialog v-if="quickEntryDt" :dt="quickEntryDt" :preset="quickEntryPreset" :workspace="workspace"
      mode="link" @close="quickEntryDt = null" @saved="onQuickEntrySaved" />

    <!-- Modals -->
    <FormModals v-model:show-delete="showDeleteModal" v-model:show-leave="showLeaveModal" @confirm-delete="handleDelete"
      @confirm-leave="confirmLeave" @cancel-leave="cancelLeave" />
  </div>
</template>

<style>
@keyframes field-shake {

  0%,
  100% {
    transform: translateX(0);
  }

  20%,
  60% {
    transform: translateX(-4px);
  }

  40%,
  80% {
    transform: translateX(4px);
  }
}

.field-shake {
  animation: field-shake 0.4s ease;
}
</style>
