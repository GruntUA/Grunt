<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick, provide } from 'vue'
import { useRouter, onBeforeRouteLeave } from 'vue-router'
import { useDocTypeStore } from '@/stores/doctype'
import { useDocument } from '@/core/composables/useDocument'
import { useToast } from '@/core/composables/useToast'
import { useWebSocket } from '@/core/composables/useWebSocket'
import { usePresence } from '@/core/composables/usePresence'
import { useClientScripts } from '@/core/composables/useClientScripts'
import { useLinkCreate } from '@/core/composables/useLinkCreate'
import { useQueryClient } from '@tanstack/vue-query'
import { clearScriptCache } from '@/core/scripting/executor'
import type { DocType, GruntDocument } from '@/types'
import { Spinner } from '@/components/ui/spinner'
import { History } from 'lucide-vue-next'

import FormRenderer from '@/core/renderer/FormRenderer.vue'
import DocSidebar from '@/components/views/DocSidebar.vue'
import VersionHistoryPanel from '@/components/views/VersionHistoryPanel.vue'

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
const validationErrors = ref<Record<string, string>>({})

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
  save: () => handleSave(),
})

// Provide link filter resolver to all descendant Link fields via inject
provide('getLinkFilters', getLinkFilters)

// ── Modals & Navigation ──────────────────────────────────────────────────────
const showDeleteModal = ref(false)
const showLeaveModal = ref(false)
let pendingRoute: string | null = null
let allowLeave = false

const showVersions = ref(false)

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

/**
 * Handle "create-new" event from a Link field inside the form.
 * Saves the current form data as a draft and navigates to the linked doc form.
 */
function handleCreateNew(linkedDoctype: string, preset: string, fieldname: string) {
  allowLeave = true
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

// ── WebSocket real-time + presence ───────────────────────────────────────────
const wsUrl = computed(() => props.id ? `/api/v1/ws/${props.doctype}/${props.id}` : null)
const docWs = useWebSocket(wsUrl)
const { lastMessage } = docWs
const { users: presenceUsers, fieldLocks, focusField, blurField } = usePresence(docWs)

watch(lastMessage, (msg) => {
  if (!msg || typeof msg !== 'object') return
  const m = msg as Record<string, unknown>
  if (m.event === 'doc_change' && !isDirty.value) {
    toast.info('Документ оновлено іншим користувачем')
    queryClient.invalidateQueries({ queryKey: ['document', props.doctype, props.id] })
  }
})

const docTitle = computed(() => {
  if (!document.value) return props.id ? '...' : `Новий ${dt.value?.label ?? ''}`
  const tf = dt.value?.title_field
  if (dt.value?.is_singleton && !tf) return dt.value.label
  return (tf && document.value[tf] as string) || document.value.name || `Новий ${dt.value?.label ?? ''}`
})

function focusFirstError() {
  nextTick(() => {
    const firstKey = Object.keys(validationErrors.value)[0]
    if (!firstKey) return
    const el = window.document.querySelector(`[data-fieldname="${firstKey}"]`) as HTMLElement | null
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el.classList.add('field-shake')
    el.addEventListener('animationend', () => el.classList.remove('field-shake'), { once: true })
    const input = el.querySelector('input, textarea, select, [contenteditable]') as HTMLElement | null
    input?.focus()
  })
}

async function handleSave() {
  validationErrors.value = {}
  const valid = await runScriptEvent('validate')
  if (valid === false) return

  await runScriptEvent('before_save')

  try {
    const saved = await save()
    toast.success('Збережено')
    runScriptEvent('after_save')
    dtStore.invalidate(props.doctype)
    queryClient.invalidateQueries({ queryKey: ['documents', props.doctype] })
    if (props.doctype === 'ClientScript') clearScriptCache()
    
    if (!props.id) {
      allowLeave = true
      const savedDoc = saved as { id: string; name: string }
      // If this save is part of a link-create flow — navigate back to origin
      if (finishLinkCreate(props.doctype, savedDoc.name)) return
      const path = props.workspace
        ? `/${props.workspace}/list/${props.doctype}/${savedDoc.id}`
        : `/${props.doctype}/${savedDoc.id}`
      router.replace(path)
    }
  } catch (err: unknown) {
    const e = err as { response?: { status?: number; data?: { detail?: string | string[] } } }
    if (e?.response?.status === 422) {
      const detail = e.response.data?.detail
      const details: string[] = Array.isArray(detail) ? detail : (typeof detail === 'string' ? [detail] : [])
      let hasFieldErrors = false
      details.forEach((d: string) => {
        const match = d.match(/^([a-z_]+):\s*(.+)$/)
        if (match) {
          validationErrors.value[match[1]] = match[2]
          hasFieldErrors = true
        }
      })
      if (hasFieldErrors) {
        toast.error('Перевірте правильність заповнення')
        focusFirstError()
      } else if (details.length > 0) {
        toast.error(details.join('; '))
      } else {
        toast.error('Помилка валідації')
      }
    } else {
      toast.error('Помилка збереження')
    }
  }
}

async function handleDelete() {
  try {
    await remove()
    toast.success('Видалено')
    queryClient.invalidateQueries({ queryKey: ['documents', props.doctype] })
    router.push(props.workspace ? `/${props.workspace}/list/${props.doctype}` : `/${props.doctype}`)
  } catch {
    toast.error('Помилка видалення')
  }
  showDeleteModal.value = false
}

onBeforeRouteLeave((to, _from, next) => {
  if (allowLeave || !isDirty.value) {
    next()
  } else {
    showLeaveModal.value = true
    pendingRoute = to.fullPath
    next(false)
  }
})

function confirmLeave() {
  showLeaveModal.value = false
  allowLeave = true
  if (pendingRoute) {
    router.push(pendingRoute)
    pendingRoute = null
  }
}

function handleDuplicate() {
  const clone = { ...form.value }
  const protectedFields = ['id', 'name', 'created_at', 'updated_at', 'owner', 'modified_by', 'workflow_state']
  protectedFields.forEach(f => delete clone[f])

  const path = props.workspace
    ? `/${props.workspace}/list/${props.doctype}/new`
    : `/${props.doctype}/new`

  allowLeave = true
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
    <FormHeader
      :dt="dt"
      :doctype="doctype"
      :id="id"
      :workspace="workspace"
      :doc-title="docTitle"
      :document="document"
      :is-dirty="isDirty"
      :is-loading="isLoading"
      :is-saving="isSaving"
      :script-buttons="scriptButtons"
      @save="handleSave"
      @delete="showDeleteModal = true"
      @duplicate="handleDuplicate"
      @invalidate="queryClient.invalidateQueries({ queryKey: ['document', props.doctype, props.id] })"
    />

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
            <FormRenderer
              :doctype="dt"
              :model-value="form"
              :disabled="isSaving"
              :errors="validationErrors"
              :overrides="displayOverrides"
              :reqd-overrides="reqdOverrides"
              :field-locks="fieldLocks"
              @update:model-value="onFormUpdate($event)"
              @field-focus="focusField($event)"
              @field-blur="blurField($event)"
              @create-new="handleCreateNew"
            />
          </div>


          <!-- Version history -->
          <div v-if="id && dt?.track_changes" class="form-section">
            <button type="button"
              class="form-section-header w-full hover:bg-muted/70 transition-colors"
              @click="showVersions = !showVersions">
              <History class="size-3.5 text-muted-foreground" />
              <span class="flex-1 text-left">Версії документа</span>
              <div class="size-4 flex items-center justify-center transition-transform duration-300" :class="{ 'rotate-180': showVersions }">
                <svg width="10" height="6" viewBox="0 0 10 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 1L5 5L9 1"/></svg>
              </div>
            </button>
            <div v-if="showVersions">
              <VersionHistoryPanel :doctype="doctype" :doc-id="id" @restored="onVersionRestored" />
            </div>
          </div>
        </div>

        <!-- Right Column: Sidebar -->
        <DocSidebar
          v-if="id && document"
          :doctype="dt"
          :document="document as GruntDocument"
          :workspace="workspace"
          :users="presenceUsers"
          class="lg:sticky lg:top-8 lg:self-start hidden lg:block"
        />
      </div>
    </template>

    <!-- Modals -->
    <FormModals
      v-model:show-delete="showDeleteModal"
      v-model:show-leave="showLeaveModal"
      @confirm-delete="handleDelete"
      @confirm-leave="confirmLeave"
      @cancel-leave="showLeaveModal = false"
    />
  </div>
</template>

<style>
@keyframes field-shake {
  0%, 100% { transform: translateX(0); }
  20%, 60% { transform: translateX(-4px); }
  40%, 80% { transform: translateX(4px); }
}
.field-shake { animation: field-shake 0.4s ease; }
</style>
