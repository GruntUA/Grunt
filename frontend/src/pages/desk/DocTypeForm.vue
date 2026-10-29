<script setup lang="ts">
import { computed, reactive, useTemplateRef, watch } from 'vue'
import { useElementSize } from '@vueuse/core'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { setPageTitle } from '@/core/composables/usePageTitle'
import { useToast } from '@/core/composables/useToast'
import { useFormController } from '@/core/composables/useFormController'
import { formatRelative } from '@/core/datetime'
import type { GruntDocument } from '@/types'
import { Activity, TriangleAlert, FlaskConical, History } from '@lucide/vue'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'

import FormRenderer from '@/core/renderer/FormRenderer.vue'
import DocSidebar from '@/components/views/DocSidebar.vue'
import QuickEntryDialog from '@/components/views/QuickEntryDialog.vue'
import SidebarTimeline from '@/components/views/sidebar/SidebarTimeline.vue'

import FormHeader from '@/components/views/form/FormHeader.vue'
import FormModals from '@/components/views/form/FormModals.vue'
import FormTour from '@/components/views/form/FormTour.vue'
import FormDashboard from '@/components/views/form/FormDashboard.vue'
import FormViewInfo from '@/components/views/form/FormViewInfo.vue'
import { isDashboardEmpty } from '@/core/scripting/formDashboard'
import { Spinner } from '@/components/ui/spinner'
import { docUrl } from '@/core/workspaceUrl'

const props = defineProps<{ doctype: string; id: string | null; workspace?: string }>()
const emit = defineEmits<{
  loaded: [payload: { doctype: string; id: string; title: string }]
  notfound: [payload: { doctype: string; id: string }]
}>()

const router = useRouter()
const toast = useToast()
const { t } = useI18n()

// The sticky FormHeader wraps onto two rows on phones, so the RichText toolbar
// offset under it is measured rather than hard-coded.
const rootEl = useTemplateRef<HTMLElement>('rootEl')
const { height: headerHeight } = useElementSize(
  () => rootEl.value?.firstElementChild as HTMLElement | undefined,
  undefined,
  { box: 'border-box' },
)

const {
  dt,
  form,
  document,
  docTitle,
  activeTab,
  activeTour,
  finishTour,
  revealField,
  isLoading,
  isDirty,
  isSaving,
  perms,
  pendingDraft,
  restoreDraft,
  discardDraft,
  validationErrors,
  actions,
  showRenameDialog,
  showShareDialog,
  showLinksDialog,
  showActivityLog,
  transitions,
  pendingTransition,
  transitionError,
  transitionBusy,
  applyTransition,
  displayOverrides,
  reqdOverrides,
  dfPropOverrides,
  sidebarHidden,
  dashboard,
  presenceUsers,
  fieldLocks,
  focusField,
  blurField,
  showDeleteModal,
  showLeaveModal,
  quickEntryDt,
  quickEntryPreset,
  handleDelete,
  onVersionRestored,
  onFormUpdate,
  handleCreateNew,
  onQuickEntrySaved,
  closeQuickEntry,
  confirmLeave,
  cancelLeave,
  rename,
  setTableSelection,
  handleSave,
} = useFormController(
  { doctype: props.doctype, id: props.id, workspace: props.workspace },
  {
    onLoaded: (payload) => emit('loaded', payload),
    onNotFound: (payload) => emit('notfound', payload),
  },
)

// Browser-tab title: the document's own title (falls back to its id), with the
// DocType label appended; "New <label>" while creating.
watch(
  [docTitle, dt, () => props.id],
  () => {
    const label = dt.value?.label || props.doctype
    const name = props.id ? (docTitle.value || props.id) : t('New')
    setPageTitle(name && name !== label ? `${name} · ${label}` : label)
  },
  { immediate: true },
)

async function onRename(newId: string) {
  try {
    await rename(newId)
    router.push(docUrl(props.doctype, newId, props.workspace))
    toast.success(t('Document renamed'))
  } catch (e: any) {
    toast.error(e.response?.data?.detail || e.message)
  }
}

// Workflow bar state (the transitions themselves are actions - global_form.js).
const workflowUi = reactive({
  transitions,
  pending: pendingTransition,
  error: transitionError,
  busy: transitionBusy,
  apply: applyTransition,
  close: () => { pendingTransition.value = null },
})

// Sidebar visibility: a client script (`frm.hide_sidebar()` / `frm.toggle_sidebar()`)
// wins; otherwise the DocType's `form_show_sidebar` config (default: shown).
const showSidebar = computed(() => {
  if (sidebarHidden.value !== null) return !sidebarHidden.value
  return dt.value?.form_show_sidebar !== false
})

// Sidebar image: the DocType's `image_field`, editable when the field is.
const imageField = computed(() => {
  const name = dt.value?.image_field
  return name ? dt.value?.fields.find((f) => f.fieldname === name) ?? null : null
})
const sidebarImage = computed(() => {
  const val = imageField.value ? form.value[imageField.value.fieldname] : null
  return typeof val === 'string' && val ? val : null
})
const sidebarImageEditable = computed(() => !!imageField.value && perms.value.write && !imageField.value.read_only && !isSaving.value)
// A new document gets the sidebar too when there is a cover to pick - it only
// shows the image there (assignees, tags... need a saved document).
const sidebarVisible = computed(() => showSidebar.value && (props.id ? !!document.value : !!imageField.value))
// Saved right away, like any other sidebar action - unless the form already
// has unsaved edits (or is a new document), which the user saves together.
async function setSidebarImage(url: string | null) {
  const field = imageField.value?.fieldname
  if (!field) return
  const wasDirty = isDirty.value
  onFormUpdate({ [field]: url })
  if (!props.id) return
  if (wasDirty) toast.info(t('Image changed. Save the document to apply it.'))
  else await handleSave()
}

</script>

<template>
  <div ref="rootEl" class="flex flex-1 flex-col" :style="{ '--richtext-sticky-top': `${headerHeight}px` }">
    <!-- Sticky header: breadcrumb + actions + document title -->
    <FormHeader :doc-title="docTitle || doctype" :dt="dt" :doctype="doctype" :id="id" :workspace="workspace" :document="form" :actions="actions" :workflow="workflowUi" :is-dirty="isDirty"
      :is-loading="isLoading" :hide-panel-toggle="!sidebarVisible"
      v-model:share-open="showShareDialog" v-model:rename-open="showRenameDialog" v-model:links-open="showLinksDialog"
      @rename="onRename" />

    <div class="flex flex-1 flex-col gap-4 sm:gap-5 p-3 sm:p-6 lg:p-8 animate-in fade-in duration-500">
    <!-- Loading -->
    <div v-if="isLoading || !dt" class="flex justify-center py-24">
      <Spinner class="!size-10" />
    </div>

    <template v-else>
      <!-- Unsaved-changes draft recovery -->
      <div v-if="pendingDraft"
        class="flex items-center gap-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-foreground">
        <History class="size-4 shrink-0 text-primary" />
        <span class="flex-1">{{ t('Unsaved changes found ({time}). Restore the draft?', { time: formatRelative(pendingDraft.savedAt) }) }}</span>
        <Button size="sm" variant="outline" @click="restoreDraft">{{ t('Restore') }}</Button>
        <Button size="sm" variant="ghost" @click="discardDraft">{{ t('Discard') }}</Button>
      </div>

      <!-- Lifecycle markers -->
      <Alert v-if="dt.deprecated"
        class="border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-200">
        <TriangleAlert />
        <AlertDescription class="text-current">{{ t('This document type is deprecated. It still works, but do not use it in new code.') }}</AlertDescription>
      </Alert>
      <Alert v-if="dt.beta" class="bg-muted/50">
        <FlaskConical />
        <AlertDescription>{{ t('Beta: this document type is still in development; its behavior may change.') }}</AlertDescription>
      </Alert>

      <div class="grid grid-cols-1 lg:grid-cols-[1fr_auto] gap-5">
        <!-- Left Column -->
        <div class="min-w-0 flex flex-col gap-4">
          <!-- Form Dashboard -->
          <FormDashboard
            v-if="dashboard && !isDashboardEmpty(dashboard)"
            :dashboard="dashboard"
            :doctype="dt"
            :document="form"
            :workspace="workspace"
            @create-new="handleCreateNew"
          />

          <!-- Main Form Card -->
          <!-- overflow-clip, not -hidden: keeps sticky children (RichText toolbar) working; offset = FormHeader height -->
          <div class="bg-card border border-border rounded-md shadow-sm p-3 sm:p-5 overflow-clip">
            <FormRenderer :doctype="dt" :model-value="form" :disabled="isSaving || !perms.write" :errors="validationErrors"
              v-model:active-tab="activeTab" :workspace="workspace"
              :overrides="displayOverrides" :reqd-overrides="reqdOverrides" :df-prop-overrides="dfPropOverrides" :field-locks="fieldLocks"
              @update:model-value="onFormUpdate" @field-focus="focusField"
              @field-blur="blurField" @create-new="handleCreateNew"
              @table-selection-change="({ fieldname, rowNames }) => setTableSelection(fieldname, rowNames)" />
          </div>


          <FormViewInfo v-if="id" :dt="dt" :id="id" />

          <!-- Activity timeline -->
          <div v-if="showActivityLog && id && document" class="form-section">
            <div class="form-section-header">
              <Activity class="size-3.5 text-muted-foreground" />
              <span class="flex-1 text-left">{{ t('Activity') }}</span>
            </div>
            <div class="form-section-body p-4!">
              <SidebarTimeline :doctype="dt" :document="document as GruntDocument" @restored="onVersionRestored" />
            </div>
          </div>
        </div>

        <!-- Right Column: Sidebar -->
        <DocSidebar v-if="sidebarVisible" :doctype="dt" :document="(id ? document : form) as GruntDocument" :is-new="!id"
          :workspace="workspace" :users="presenceUsers" :image-url="sidebarImage" :image-editable="sidebarImageEditable"
          class="lg:sticky lg:top-14 lg:self-start" @set-image="setSidebarImage" />
      </div>
    </template>
    </div>

    <!-- Quick Entry Dialog (from Link field) -->
    <QuickEntryDialog v-if="quickEntryDt" :dt="quickEntryDt" :preset="quickEntryPreset" :workspace="workspace"
      mode="link" @close="closeQuickEntry" @saved="onQuickEntrySaved" />

    <!-- Modals -->
    <FormTour v-if="activeTour" :key="activeTour.name" :tour="activeTour" :reveal="revealField" @close="finishTour" />
    <FormModals v-model:show-delete="showDeleteModal" v-model:show-leave="showLeaveModal" :doctype="doctype"
      :doc-id="id" @confirm-delete="handleDelete" @confirm-leave="confirmLeave" @cancel-leave="cancelLeave" />
  </div>
</template>

