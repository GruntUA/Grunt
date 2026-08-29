<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useQueryClient } from '@tanstack/vue-query'
import { useToast } from '@/core/composables/useToast'
import { useFormController } from '@/core/composables/useFormController'
import type { GruntDocument } from '@/types'
import { History, Activity } from '@lucide/vue'

import FormRenderer from '@/core/renderer/FormRenderer.vue'
import DocSidebar from '@/components/views/DocSidebar.vue'
import VersionHistoryPanel from '@/components/views/VersionHistoryPanel.vue'
import QuickEntryDialog from '@/components/views/QuickEntryDialog.vue'
import SidebarTimeline from '@/components/views/sidebar/SidebarTimeline.vue'

import FormHeader from '@/components/views/form/FormHeader.vue'
import FormModals from '@/components/views/form/FormModals.vue'
import DocDashboard from '@/components/views/form/DocDashboard.vue'
import { Spinner } from '@/components/ui/spinner'

const props = defineProps<{ doctype: string; id: string | null; workspace?: string }>()
const emit = defineEmits<{
  loaded: [payload: { doctype: string; id: string; title: string }]
  notfound: [payload: { doctype: string; id: string }]
}>()

const router = useRouter()
const toast = useToast()
const queryClient = useQueryClient()
const { t } = useI18n()

// Local UI-only state not owned by the form controller
const showActivityLog = ref(true)

const {
  dt,
  form,
  document,
  docTitle,
  activeTab,
  isLoading,
  isDirty,
  isSaving,
  validationErrors,
  scriptButtons,
  scriptMenuItems,
  displayOverrides,
  reqdOverrides,
  dfPropOverrides,
  sidebarHidden,
  presenceUsers,
  fieldLocks,
  focusField,
  blurField,
  showDeleteModal,
  showLeaveModal,
  showVersions,
  quickEntryDt,
  quickEntryPreset,
  handleSave,
  handleDelete,
  handleDuplicate,
  onVersionRestored,
  onFormUpdate,
  handleCreateNew,
  onQuickEntrySaved,
  closeQuickEntry,
  confirmLeave,
  cancelLeave,
  rename,
  setTableSelection,
} = useFormController(
  { doctype: props.doctype, id: props.id, workspace: props.workspace },
  {
    onLoaded: (payload) => emit('loaded', payload),
    onNotFound: (payload) => emit('notfound', payload),
  },
)

// Sidebar visibility: a client script (`frm.hide_sidebar()` / `frm.toggle_sidebar()`)
// wins; otherwise the DocType's `form_view.show_sidebar` config (default: shown).
const showSidebar = computed(() => {
  if (sidebarHidden.value !== null) return !sidebarHidden.value
  return dt.value?.form_view?.show_sidebar !== false
})
</script>

<template>
  <div class="flex flex-1 flex-col gap-5 p-4 sm:p-6 lg:p-8 animate-in fade-in duration-500">
    <!-- Header -->
    <FormHeader :doc-title="docTitle || doctype" :dt="dt" :doctype="doctype" :id="id" :document="form" :is-dirty="isDirty"
      :is-loading="isLoading" :is-saving="isSaving" :script-buttons="scriptButtons" :script-menu-items="scriptMenuItems"
      :hide-panel-toggle="!showSidebar"
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
      <Spinner class="!size-10" />
    </div>

    <template v-else>
      <div class="grid grid-cols-1 lg:grid-cols-[1fr_auto] gap-5">
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
        <DocSidebar v-if="id && document && showSidebar" :doctype="dt" :document="document as GruntDocument"
          :workspace="workspace" :users="presenceUsers" class="lg:sticky lg:top-8 lg:self-start" />
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
