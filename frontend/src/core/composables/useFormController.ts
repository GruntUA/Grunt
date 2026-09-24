/**
 * useFormController — unified form lifecycle facade.
 *
 * Orchestrates document loading, dirty-state tracking, client-script execution,
 * field validation, saving, navigation guards, real-time sync, presence,
 * version control, and quick-entry link creation behind a single composable
 * surface. Consumers only wire up their domain-specific callbacks (e.g. toasts,
 * router) instead of reaching into eight separate composables.
 */
import { computed, onMounted, provide, ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'

import { useDocTypeStore } from '@/stores/doctype'
import { useAuthStore } from '@/stores/auth'
import { useDocument } from '@/core/composables/useDocument'
import { useFormDraft } from '@/core/composables/useFormDraft'
import { useToast } from '@/core/composables/useToast'
import { useWebSocket } from '@/core/composables/useWebSocket'
import { usePresence } from '@/core/composables/usePresence'
import { useClientScripts } from '@/core/composables/useClientScripts'
import { useDocActions } from '@/core/composables/useDocActions'
import { useLinkCreate } from '@/core/composables/useLinkCreate'
import { useFetchFrom } from '@/core/composables/useFetchFrom'
import { useQueryClient } from '@tanstack/vue-query'

import { useFormValidation } from './useFormValidation'
import { useFormDocWatcher } from './useFormDocWatcher'
import { useFormNavigation } from './useFormNavigation'
import { useFormSave } from './useFormSave'
import { useFormInitialization } from './useFormInitialization'
import { useFormActions } from './useFormActions'
import { useFormLinkCreation } from './useFormLinkCreation'
import { useFormDocumentView } from './useFormDocumentView'
import { useFormShortcuts } from './useFormShortcuts'

import type { DocType } from '@/types'
import { docUrl } from '@/core/workspaceUrl'
import { formPermissions } from '@/core/permissions'

// ── Public interface ─────────────────────────────────────────────────────────

export interface UseFormControllerOptions {
  /** The machine-name of the DocType being edited. */
  doctype: string
  /** The document ID being edited, or null for a new (unsaved) document. */
  id: string | null
  /** Optional workspace prefix for URL generation. */
  workspace?: string
}

export interface UseFormControllerEmits {
  /** Called once an existing document has loaded so callers can track it. */
  onLoaded?: (payload: { doctype: string; id: string; title: string }) => void
  /** Called when an existing document fails to load (e.g. deleted). */
  onNotFound?: (payload: { doctype: string; id: string }) => void
}

// ── Composable ───────────────────────────────────────────────────────────────

export function useFormController(
  options: UseFormControllerOptions,
  emits: UseFormControllerEmits = {},
) {
  const { doctype, id, workspace } = options

  const router = useRouter()
  const route = useRoute()
  const dtStore = useDocTypeStore()
  const toast = useToast()
  const queryClient = useQueryClient()

  // ── DocType metadata ───────────────────────────────────────────────────────
  const dt = ref<DocType | null>(null)

  // ── Document data + CRUD primitives ───────────────────────────────────────
  const { document, form, isLoading, isError, isDirty, isSaving, save, remove, rename, markClean } =
    useDocument(doctype, id)

  // ── Unsaved-changes draft (survives accidental reload/close) ───────────────
  const { pendingDraft, checkForDraft, restoreDraft, discardDraft } = useFormDraft({
    doctype,
    id,
    form,
    isDirty,
  })

  // ── Active tab — synced to URL query (?tab=...) ────────────────────────────
  const activeTab = computed<string>({
    get: () => (route.query.tab as string) || '',
    set: (val) => {
      void router.replace({ query: { ...route.query, tab: val || undefined } })
    },
  })

  // ── Real-time WebSocket + presence ─────────────────────────────────────────
  const wsUrl = computed(() => (id ? `/api/v1/ws/${doctype}/${id}` : null))
  const docWs = useWebSocket(wsUrl)
  const { lastMessage } = docWs
  const { users: presenceUsers, fieldLocks, focusField, blurField } = usePresence(docWs)

  // ── Client scripts ─────────────────────────────────────────────────────────
  // Deferred reference so the save handler can call itself via client scripts.
  let _saveHandler: (() => Promise<void>) | null = null

  const {
    buttons: scriptButtons,
    menuItems: scriptMenuItems,
    displayOverrides,
    reqdOverrides,
    dfPropOverrides,
    sidebarHidden,
    runEvent: runScriptEvent,
    getLinkFilters,
    setTableSelection,
  } = useClientScripts(doctype, {
    getDoc: () => form.value,
    getFields: () => (dt.value?.fields ?? []) as Record<string, unknown>[],
    isNew: () => !id,
    setValue: (field, value) => {
      form.value[field] = value
    },
    reload: async () => {
      if (id) {
        await queryClient.invalidateQueries({ queryKey: ['document', doctype, id] })
      }
    },
    save: async () => {
      if (_saveHandler) await _saveHandler()
    },
    markClean,
    lastMessage,
  })

  // ── Declarative document actions (DocType.actions bindings) ────────────────
  const { docActionButtons } = useDocActions({
    doctype,
    id,
    dt,
    form: () => form.value,
    reload: async () => {
      if (id) await queryClient.invalidateQueries({ queryKey: ['document', doctype, id] })
    },
  })

  // Registry-bound action buttons render first, then client-script buttons.
  const allButtons = computed(() => [...docActionButtons.value, ...(scriptButtons.value ?? [])])

  // ── Validation ─────────────────────────────────────────────────────────────
  const { validationErrors, focusFirstError, validateForm } = useFormValidation({
    doctype,
    dt,
    form,
    displayOverrides,
    reqdOverrides,
    toast,
    activeTab,
  })

  // ── Link creation (quick entry + full navigation) ──────────────────────────
  const { startLinkCreate, finishLinkCreate, restoreLinkDraft } = useLinkCreate()

  const showDeleteModal = ref(false)

  const {
    quickEntryDt,
    quickEntryPreset,
    isQuickEntryOpen,
    handleCreateNew,
    onQuickEntrySaved,
    closeQuickEntry,
  } = useFormLinkCreation({
    doctype,
    id,
    workspace,
    form,
    markAllowLeave: () => markAllowLeave(),
    loadDocType: (name: string) => dtStore.get(name),
    startLinkCreate: ({ linkedDoctype, preset, fieldname, parentDoctype, parentId, formSnapshot, workspace: ws }) => {
      startLinkCreate(linkedDoctype, preset, fieldname, parentDoctype, parentId, formSnapshot, ws)
    },
    navigateToNew: (linkedDoctype, preset) => {
      const query: Record<string, string> = {}
      for (const [k, v] of Object.entries(preset)) {
        query[k] = String(v)
      }
      void router.push({ path: docUrl(linkedDoctype, 'new', workspace), query })
    },
  })

  // ── Navigation guard (dirty leave warning + Escape shortcut) ───────────────
  const { showLeaveModal, markAllowLeave, confirmLeave, cancelLeave, goToList } = useFormNavigation({
    router,
    doctype,
    workspace,
    isDirty,
    showDeleteModal,
    isQuickEntryOpen,
  })

  // ── WebSocket doc-change watcher ───────────────────────────────────────────
  useFormDocWatcher({ lastMessage, isDirty, doctype, id, queryClient, toast })

  // ── Save ───────────────────────────────────────────────────────────────────
  const { handleSave } = useFormSave({
    doctype,
    id,
    workspace,
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
  _saveHandler = handleSave

  // ── Initialization (defaults, URL params, duplicate, on_load) ──────────────
  const { initialize } = useFormInitialization({
    doctype,
    id,
    dt,
    form,
    loadDocType: async (name: string) => {
      if (name === doctype) dtStore.invalidate(name)
      return dtStore.get(name)
    },
    restoreLinkDraft,
    info: (message: string) => toast.info(message),
    runOnLoad: () => runScriptEvent('on_load'),
    checkForDraft,
  })

  // ── Delete / Duplicate / Version restore ───────────────────────────────────
  const { onVersionRestored, handleDelete, handleDuplicate } = useFormActions({
    doctype,
    id,
    workspace,
    form,
    showDeleteModal,
    remove,
    goToList,
    markAllowLeave,
    router,
    queryClient,
    toast,
  })

  // ── Title + reactive form update (triggers on_change scripts) ──────────────
  const { docTitle, onFormUpdate } = useFormDocumentView({
    id,
    dt,
    document: computed(() => (document.value as Record<string, unknown> | null)),
    form,
    runOnChange: (field) => {
      void runScriptEvent('on_change', field)
    },
  })

  // ── Permissions (server's __perms, or role rows for a new document) ────────
  const auth = useAuthStore()
  const perms = computed(() =>
    formPermissions(dt.value, document.value as Record<string, unknown> | null, !id, auth.user?.roles ?? []),
  )

  // ── Keyboard shortcuts (Ctrl+S, Ctrl+P) ────────────────────────────────────
  useFormShortcuts({
    onSave: () => { if (perms.value.write) void handleSave() },
    onPrint: () => { window.print() },
  })

  // ── fetch_from field population ────────────────────────────────────────────
  useFetchFrom({
    doctype: dt,
    modelValue: form,
    updateField: (fieldname, value) => {
      form.value[fieldname] = value
    },
  })

  // ── Provide link-filter resolver to all descendant Link fields ─────────────
  provide('getLinkFilters', getLinkFilters)
  provide('docContext', { doctype, getId: () => id })

  // ── Lifecycle ──────────────────────────────────────────────────────────────
  onMounted(async () => {
    await initialize()
  })

  // Re-run on_load once document data arrives from the server.
  // initialize() fires on_load before the async fetch completes, so frm.doc
  // fields are empty on first call. This watcher catches the "fresh load" case.
  if (id) {
    const unwatchDoc = watch(document, async (doc) => {
      if (doc) {
        unwatchDoc()
        emits.onLoaded?.({ doctype, id, title: docTitle.value })
        checkForDraft()
        await runScriptEvent('on_load')
      }
    })

    const unwatchErr = watch(isError, (failed) => {
      if (failed) {
        unwatchErr()
        emits.onNotFound?.({ doctype, id })
      }
    })
  }

  // ── Public surface ─────────────────────────────────────────────────────────
  return {
    // State
    dt,
    form,
    document,
    docTitle,
    activeTab,
    isLoading,
    isError,
    isDirty,
    isSaving,
    perms,

    // Unsaved-changes draft
    pendingDraft,
    restoreDraft,
    discardDraft,

    // Validation
    validationErrors,

    // Client scripts (+ declarative DocType.actions bindings, prepended)
    scriptButtons: allButtons,
    scriptMenuItems,
    displayOverrides,
    reqdOverrides,
    dfPropOverrides,
    sidebarHidden,

    // Presence / Real-time
    presenceUsers,
    fieldLocks,
    focusField,
    blurField,

    // Modals
    showDeleteModal,
    showLeaveModal,

    // Quick entry
    quickEntryDt,
    quickEntryPreset,
    isQuickEntryOpen,

    // Actions
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
    goToList,
    rename,
    setTableSelection,
  }
}
