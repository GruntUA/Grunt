<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { setPageTitle } from '@/core/composables/usePageTitle'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { useToast } from '@/core/composables/useToast'
import { useFormController } from '@/core/composables/useFormController'
import { docsApi } from '@/core/api/docs'
import { formatRelative } from '@/core/datetime'
import type { GruntDocument } from '@/types'
import { Activity, Eye, TriangleAlert, FlaskConical, History } from '@lucide/vue'
import { Button } from '@/components/ui/button'

import FormRenderer from '@/core/renderer/FormRenderer.vue'
import DocSidebar from '@/components/views/DocSidebar.vue'
import QuickEntryDialog from '@/components/views/QuickEntryDialog.vue'
import SidebarTimeline from '@/components/views/sidebar/SidebarTimeline.vue'

import FormHeader from '@/components/views/form/FormHeader.vue'
import FormModals from '@/components/views/form/FormModals.vue'
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
  pendingDraft,
  restoreDraft,
  discardDraft,
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

// Sidebar visibility: a client script (`frm.hide_sidebar()` / `frm.toggle_sidebar()`)
// wins; otherwise the DocType's `form_show_sidebar` config (default: shown).
const showSidebar = computed(() => {
  if (sidebarHidden.value !== null) return !sidebarHidden.value
  return dt.value?.form_show_sidebar !== false
})

// Seen / views (only fetched when the DocType opts into track_seen / track_views)
const tracksViews = computed(() => !!(dt.value?.track_seen || dt.value?.track_views))
const { data: viewInfo } = useQuery({
  queryKey: computed(() => ['view-info', props.doctype, props.id]),
  queryFn: () => docsApi.getViewInfo(props.doctype, props.id!),
  enabled: computed(() => !!props.id && tracksViews.value),
})
const seenList = computed<string[]>(() => viewInfo.value?.seen ?? [])
const seenShown = computed(() => seenList.value.slice(0, 6))
const initials = (email: string) => email.slice(0, 2).toUpperCase()
</script>

<template>
  <div class="flex flex-1 flex-col">
    <!-- Sticky header: breadcrumb + actions + document title -->
    <FormHeader :doc-title="docTitle || doctype" :dt="dt" :doctype="doctype" :id="id" :workspace="workspace" :document="form" :is-dirty="isDirty"
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

    <div class="flex flex-1 flex-col gap-5 p-4 sm:p-6 lg:p-8 animate-in fade-in duration-500">
    <!-- Loading -->
    <div v-if="isLoading || !dt" class="flex justify-center py-24">
      <Spinner class="!size-10" />
    </div>

    <template v-else>
      <!-- Unsaved-changes draft recovery -->
      <div v-if="pendingDraft"
        class="flex items-center gap-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-foreground">
        <History class="size-4 shrink-0 text-primary" />
        <span class="flex-1">{{ t('Знайдено незбережені зміни ({time}). Відновити чернетку?').replace('{time}', formatRelative(pendingDraft.savedAt)) }}</span>
        <Button size="sm" variant="outline" @click="restoreDraft">{{ t('Відновити') }}</Button>
        <Button size="sm" variant="ghost" @click="discardDraft">{{ t('Відхилити') }}</Button>
      </div>

      <!-- Lifecycle markers -->
      <div v-if="dt?.deprecated"
        class="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-amber-900 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-200">
        <TriangleAlert class="size-4 mt-0.5 shrink-0" />
        <span>{{ t('Цей тип документа позначено як неактуальний (deprecated). Він продовжує працювати, але не використовуйте його в новому коді.') }}</span>
      </div>
      <div v-if="dt?.beta"
        class="flex items-start gap-2 rounded-md border border-border bg-muted/50 px-3 py-2 text-muted-foreground">
        <FlaskConical class="size-4 mt-0.5 shrink-0" />
        <span>{{ t('Beta: цей тип документа ще в розробці, поведінка може змінитися.') }}</span>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-[1fr_auto] gap-5">
        <!-- Left Column -->
        <div class="min-w-0 flex flex-col gap-4">
          <!-- Main Form Card -->
          <div class="bg-card border border-border rounded-md shadow-sm p-5 overflow-hidden">
            <FormRenderer :doctype="dt" :model-value="form" :disabled="isSaving" :errors="validationErrors"
              v-model:active-tab="activeTab" :workspace="props.workspace"
              :overrides="displayOverrides" :reqd-overrides="reqdOverrides" :df-prop-overrides="dfPropOverrides" :field-locks="fieldLocks"
              @update:model-value="onFormUpdate($event)" @field-focus="focusField($event)"
              @field-blur="blurField($event)" @create-new="handleCreateNew"
              @table-selection-change="({ fieldname, rowNames }) => setTableSelection(fieldname, rowNames)" />
          </div>


          <!-- Seen / views -->
          <div v-if="id && tracksViews && viewInfo"
            class="flex flex-wrap items-center gap-x-4 gap-y-1.5 px-1 text-muted-foreground">
            <span v-if="dt?.track_views" class="inline-flex items-center gap-1.5">
              <Eye class="size-3.5" />
              {{ t('{views} переглядів · {viewers} користувачів').replace('{views}', String(viewInfo.views)).replace('{viewers}', String(viewInfo.viewers)) }}
            </span>
            <span v-if="dt?.track_seen && seenList.length" class="inline-flex items-center gap-1.5">
              {{ t('Переглянули:') }}
              <span class="flex -space-x-1.5">
                <span v-for="email in seenShown" :key="email" :title="email"
                  class="inline-flex size-5 items-center justify-center rounded-full border border-background bg-muted text-[9px] font-medium text-foreground">
                  {{ initials(email) }}
                </span>
              </span>
              <span v-if="seenList.length > seenShown.length">+{{ seenList.length - seenShown.length }}</span>
            </span>
          </div>

          <!-- Activity timeline -->
          <div v-if="showActivityLog && id && document" class="form-section">
            <div class="form-section-header">
              <Activity class="size-3.5 text-muted-foreground" />
              <span class="flex-1 text-left">{{ t('Активність') }}</span>
            </div>
            <div class="form-section-body p-4!">
              <SidebarTimeline :doctype="dt" :document="document as GruntDocument" @restored="onVersionRestored" />
            </div>
          </div>
        </div>

        <!-- Right Column: Sidebar -->
        <DocSidebar v-if="id && document && showSidebar" :doctype="dt" :document="document as GruntDocument"
          :workspace="workspace" :users="presenceUsers" class="lg:sticky lg:top-14 lg:self-start" />
      </div>
    </template>
    </div>

    <!-- Quick Entry Dialog (from Link field) -->
    <QuickEntryDialog v-if="quickEntryDt" :dt="quickEntryDt" :preset="quickEntryPreset" :workspace="workspace"
      mode="link" @close="closeQuickEntry" @saved="onQuickEntrySaved" />

    <!-- Modals -->
    <FormModals v-model:show-delete="showDeleteModal" v-model:show-leave="showLeaveModal" :doctype="doctype"
      :doc-id="id" @confirm-delete="handleDelete" @confirm-leave="confirmLeave" @cancel-leave="cancelLeave" />
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
