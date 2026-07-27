<script setup lang="ts">
import { ref, computed, onMounted, provide, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
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
import { useFormInitialization } from '@/core/composables/useFormInitialization'
import { useFormActions } from '@/core/composables/useFormActions'
import { useFormLinkCreation } from '@/core/composables/useFormLinkCreation'
import { useFormDocumentView } from '@/core/composables/useFormDocumentView'
import { useFormShortcuts } from '@/core/composables/useFormShortcuts'
import { useFetchFrom } from '@/core/composables/useFetchFrom'
import { useQueryClient } from '@tanstack/vue-query'
import type { DocType, GruntDocument } from '@/types'
import { History, Activity } from '@lucide/vue'
import ProgressSpinner from 'primevue/progressspinner'

import FormRenderer from '@/core/renderer/FormRenderer.vue'
import DocSidebar from '@/components/views/DocSidebar.vue'
import VersionHistoryPanel from '@/components/views/VersionHistoryPanel.vue'
import QuickEntryDialog from '@/components/views/QuickEntryDialog.vue'
import SidebarTimeline from '@/components/views/sidebar/SidebarTimeline.vue'

// Custom sub-components
import FormHeader from '@/components/views/form/FormHeader.vue'
import FormModals from '@/components/views/form/FormModals.vue'
import DocDashboard from '@/components/views/form/DocDashboard.vue'

const props = defineProps<{ doctype: string; id: string | null; workspace?: string }>()
const emit = defineEmits<{
  // Fired once the existing document is loaded, carrying its resolved display
  // title (title_field value, not the raw id) for recent-docs tracking.
  loaded: [payload: { doctype: string; id: string; title: string }]
  // Fired when an existing document fails to load (e.g. deleted) so callers
  // can prune stale references such as recent-docs entries.
  notfound: [payload: { doctype: string; id: string }]
}>()
const router = useRouter()
const route = useRoute()

const activeTab = computed({
  get: () => route.query.tab as string || '',
  set: (val) => {
    router.replace({ 
      query: { ...route.query, tab: val || undefined } 
    })
  }
})
const dtStore = useDocTypeStore()
const toast = useToast()
const { t } = useI18n()
const queryClient = useQueryClient()
const { startLinkCreate, finishLinkCreate, restoreLinkDraft } = useLinkCreate()

const dt = ref<DocType | null>(null)
const { document, form, isLoading, isError, isDirty, isSaving, save, remove, rename, markClean } = useDocument(props.doctype, props.id)

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
  dfPropOverrides,
  runEvent: runScriptEvent,
  getLinkFilters,
  setTableSelection,
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
  markClean,
  lastMessage,
})

const {
  validationErrors,
  focusFirstError,
  validateForm,
} = useFormValidation({
  doctype: props.doctype,
  dt,
  form,
  displayOverrides,
  reqdOverrides,
  toast,
  activeTab,
})

// Provide link filter resolver to all descendant Link fields via inject
provide('getLinkFilters', getLinkFilters)
// Provide document context so Attach/Image fields can set attached_to_* on upload
provide('docContext', { doctype: props.doctype, getId: () => props.id })

// ── Modals & Navigation ──────────────────────────────────────────────────────
const showDeleteModal = ref(false)
const showActivityLog = ref(true)
const showVersions = ref(false)

const {
  quickEntryDt,
  quickEntryPreset,
  isQuickEntryOpen,
  handleCreateNew,
  onQuickEntrySaved,
  closeQuickEntry,
} = useFormLinkCreation({
  doctype: props.doctype,
  id: props.id,
  workspace: props.workspace,
  form,
  markAllowLeave: () => markAllowLeave(),
  loadDocType: (doctype: string) => dtStore.get(doctype),
  startLinkCreate: ({ linkedDoctype, preset, fieldname, parentDoctype, parentId, formSnapshot, workspace }) => {
    startLinkCreate(
      linkedDoctype,
      preset,
      fieldname,
      parentDoctype,
      parentId,
      formSnapshot,
      workspace,
    )
  },
  navigateToNew: (linkedDoctype: string, preset: Record<string, unknown>) => {
    const ws = props.workspace || 'grunt'
    const query: Record<string, string> = {}
    for (const [k, v] of Object.entries(preset)) {
      query[k] = String(v)
    }
    router.push({ path: `/${ws}/${linkedDoctype}/new`, query })
  },
})

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
  isQuickEntryOpen,
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
  form,
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

const { initialize } = useFormInitialization({
  doctype: props.doctype,
  id: props.id,
  dt,
  form,
  loadDocType: async (doctype: string) => {
    // Always refresh the main form DocType metadata to pick up recent schema changes.
    if (doctype === props.doctype) dtStore.invalidate(doctype)
    return dtStore.get(doctype)
  },
  restoreLinkDraft,
  info: (message: string) => {
    toast.info(message)
  },
  runOnLoad: () => runScriptEvent('on_load'),
})

const {
  onVersionRestored,
  handleDelete,
  handleDuplicate,
} = useFormActions({
  doctype: props.doctype,
  id: props.id,
  workspace: props.workspace,
  form,
  showDeleteModal,
  showVersions,
  remove,
  goToList,
  markAllowLeave,
  router,
  queryClient,
  toast,
})

const {
  docTitle,
  onFormUpdate,
} = useFormDocumentView({
  id: props.id,
  dt,
  document: computed(() => (document.value as Record<string, unknown> | null)),
  form,
  runOnChange: (field) => {
    void runScriptEvent('on_change', field)
  },
})

onMounted(async () => {
  await initialize()
})

// Re-run on_load once document data arrives from server.
// initialize() fires on_load before the async fetch completes, so
// frm.doc fields are empty. This watcher catches the "fresh load" case.
if (props.id) {
  const unwatchDoc = watch(document, async (doc) => {
    if (doc) {
      unwatchDoc()
      // Surface the resolved title for recent-docs tracking before running
      // on_load scripts (which may mutate fields).
      emit('loaded', { doctype: props.doctype, id: props.id!, title: docTitle.value })
      await runScriptEvent('on_load')
    }
  })

  // Prune stale references when the document can't be loaded (e.g. deleted).
  const unwatchErr = watch(isError, (failed) => {
    if (failed) {
      unwatchErr()
      emit('notfound', { doctype: props.doctype, id: props.id! })
    }
  })
}

useFormShortcuts({
  onSave: () => {
    void handleSave()
  },
  onPrint: () => {
    window.print()
  },
})

useFetchFrom({
  doctype: dt,
  modelValue: form,
  updateField: (fieldname, value) => {
    form.value[fieldname] = value
  },
})

</script>

<template>
  <div class="flex flex-1 flex-col gap-5 p-4 sm:p-6 lg:p-8 animate-in fade-in duration-500">
    <!-- Header -->
    <FormHeader :doc-title="docTitle || doctype" :dt="dt" :doctype="doctype" :id="id" :document="form" :is-dirty="isDirty"
      :is-loading="isLoading" :is-saving="isSaving" :script-buttons="scriptButtons"
      @save="handleSave" @delete="showDeleteModal = true" @duplicate="handleDuplicate"
      @toggleLog="showActivityLog = !showActivityLog"
      @rename="async (newId) => {
        try {
          await rename(newId)
          router.push({
            name: 'workspace-form',
            params: { 
              workspaceName: workspace || 'grunt', 
              doctype: doctype, 
              id: newId 
            }
          })
          toast.success(t('Document renamed'))
        } catch (e: any) {
          toast.error(e.response?.data?.detail || e.message)
        }
      }"
      @invalidate="queryClient.invalidateQueries({ queryKey: ['document', props.doctype, props.id] })" />

    <!-- Loading -->
    <div v-if="isLoading || !dt" class="flex justify-center py-24">
      <ProgressSpinner class="!size-10" />
    </div>

    <template v-else>
      <div class="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-5">
        <!-- Left Column -->
        <div class="min-w-0 flex flex-col gap-4">
          <!-- Dashboard / Connections -->
          <DocDashboard v-if="id && document && dt" :dt="dt" :document="document" :workspace="props.workspace"
            @create-new="handleCreateNew"
          />

          <!-- Main Form Card -->
          <div class="bg-card border border-border rounded-md shadow-sm p-5 overflow-hidden">
            <FormRenderer :doctype="dt" :model-value="form" :disabled="isSaving" :errors="validationErrors"
              v-model:active-tab="activeTab"
              :overrides="displayOverrides" :reqd-overrides="reqdOverrides" :df-prop-overrides="dfPropOverrides" :field-locks="fieldLocks"
              @update:model-value="onFormUpdate($event)" @field-focus="focusField($event)"
              @field-blur="blurField($event)" @create-new="handleCreateNew"
              @table-selection-change="({ fieldname, rowNames }) => setTableSelection(fieldname, rowNames)" />
          </div>


          <!-- Activity timeline -->
          <div v-if="showActivityLog && id && document" class="form-section">
            <div class="form-section-header">
              <Activity class="size-3.5 text-muted-foreground" />
              <span class="flex-1 text-left">{{ t('Активність') }}</span>
            </div>
            <div class="form-section-body p-4!">
              <SidebarTimeline :doctype="dt" :document="document as GruntDocument" />
            </div>
          </div>

          <!-- Version history -->
          <div v-if="id && dt?.track_changes" class="form-section">
            <button type="button" class="form-section-header w-full hover:bg-muted/70 transition-colors"
              @click="showVersions = !showVersions">
              <History class="size-3.5 text-muted-foreground" />
              <span class="flex-1 text-left">{{ t('version_history') }}</span>
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
      mode="link" @close="closeQuickEntry" @saved="onQuickEntrySaved" />

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
