/**
 * Composable that manages client script lifecycle for a document form.
 *
 * Wires up executor.ts with the form state, dialog system, and toasts.
 *
 * Usage in DocTypeForm.vue:
 *
 *   const scripts = useClientScripts(props.doctype, {
 *     getDoc: () => form,
 *     getFields: () => dt.value?.fields ?? [],
 *     isNew: () => !props.id,
 *     setValue: (f, v) => { form[f] = v },
 *     save: () => handleSave(),
 *   })
 *
 *   // In onMounted after loading DocType:
 *   await scripts.runEvent('on_load')
 *
 *   // Before save:
 *   const valid = await scripts.runEvent('validate')
 *
 *   // Render scripts.actions (core/actions.ts) in the header
 */

import { ref, reactive, watch } from 'vue'
import type { Ref } from 'vue'
import { useRouter } from 'vue-router'
import { useDialog } from '@/core/composables/useDialog'
import { useToast } from '@/core/composables/useToast'
import { useI18n } from 'vue-i18n'
import { createActionRegistry } from '@/core/actions'
import {
  createFormProxy,
  createGruntProxy,
  dispatchMessageToProxy,
  executeClientScripts,
  type FormProxy,
  type FormProxyState,
  type FormProxyUi,
  type GruntProxy,
  type ClientScriptEvent,
} from '@/core/scripting/executor'

export interface UseClientScriptsOptions {
  getDoc: () => Record<string, unknown>
  getFields: () => Record<string, unknown>[]
  isNew: () => boolean
  setValue: (field: string, value: unknown) => void
  refreshField?: (field: string) => void
  reload: (options?: { meta?: boolean }) => Promise<void>
  save: () => Promise<void>
  markClean?: () => void
  /** Live form state behind frm.perm / frm.is_dirty / … */
  state: () => FormProxyState
  /** Dialogs and flows the standard actions open (delete, rename, share, …). */
  ui: Partial<FormProxyUi>
  /** Reactive ref to the latest WebSocket message on the document channel */
  lastMessage?: Ref<unknown>
}

export function useClientScripts(doctype: string, options: UseClientScriptsOptions) {
  const dialog = useDialog()
  const toast = useToast()
  const router = useRouter()
  const { t } = useI18n()
  const displayOverrides = reactive<Record<string, boolean>>({})
  const reqdOverrides = reactive<Record<string, boolean>>({})
  const dfPropOverrides = reactive<Record<string, Record<string, unknown>>>({})
  // null -> scripts left the sidebar decision to form_show_sidebar
  const sidebarHidden = ref<boolean | null>(null)

  const messageListeners = new Map<string, Set<(data: unknown) => void>>()

  let gruntProxy: GruntProxy | null = null

  // Forward WS messages to grunt.onMessage subscribers
  if (options.lastMessage) {
    watch(options.lastMessage, (msg) => {
      if (!msg || typeof msg !== 'object') return
      const m = msg as Record<string, unknown>
      if (typeof m.event === 'string') {
        dispatchMessageToProxy(messageListeners, m.event, m.data ?? m)
      }
    })
  }

  // Live proxy for doc - always reads current form values
  const liveDoc = new Proxy({} as Record<string, unknown>, {
    get(_, prop: string) { return options.getDoc()[prop] },
    set(_, prop: string, val) { options.getDoc()[prop] = val; return true },
    has(_, prop: string) { return prop in options.getDoc() },
    ownKeys() { return Reflect.ownKeys(options.getDoc()) },
    getOwnPropertyDescriptor(_, prop) {
      const doc = options.getDoc()
      if (prop in doc) return { configurable: true, enumerable: true, value: doc[prop as string] }
      return undefined
    },
  })

  // Single persistent FormProxy - buttons and other closures keep a stable reference
  const frm: FormProxy = createFormProxy(
    doctype,
    liveDoc,
    options.getFields(),
    {
      setValue: (field, value) => {
        options.setValue(field, value)
      },
      refreshField: options.refreshField,
      reload: options.reload,
      save: options.save,
      markClean: options.markClean,
      state: options.state,
      ui: options.ui,
    },
    options.isNew(),
  )

  // Every button / menu item of the form (core/actions.ts) - filled by
  // global_form.js, the DocType's script and ClientScripts on on_load.
  const actions = createActionRegistry<FormProxy>(() => frm, {
    confirm: (message) => dialog.confirm(message),
    translate: (label) => t(label),
  })
  frm.actions = actions

  function ensureGrunt(): GruntProxy {
    if (!gruntProxy) {
      gruntProxy = createGruntProxy({
        msgprint: async (msgOrOpts) => {
          dialog.msgprint(
            typeof msgOrOpts === 'string'
              ? msgOrOpts
              : {
                message: msgOrOpts.message,
                title: msgOrOpts.title,
                indicator: msgOrOpts.indicator,
              }
          )
        },
        confirm: (msg) => dialog.confirm(msg),
        showAlert: (msg: string, type: 'info' | 'success' | 'error' | 'warning' = 'info') => {
          if (type === 'success') toast.success(msg)
          else if (type === 'error') toast.error(msg)
          else if (type === 'warning') toast.warning(msg)
          else toast.info(msg)
        },
        prompt: (labelOrOpts, title) => dialog.prompt(labelOrOpts as any, title),
        form: (opts) => dialog.form(opts as any),
        select: (opts) => dialog.select(opts as any),
        navigateTo: (href, inNewTab) => {
          if (inNewTab) {
            window.open(href, '_blank')
            return
          }
          router.push(href)
        },
      }, messageListeners)
    }
    return gruntProxy
  }

  /**
   * Run a client script event. Returns false if validate returns false.
   */
  async function runEvent(event: ClientScriptEvent, changedField?: string): Promise<boolean> {
    const grunt = ensureGrunt()

    // doc is live via Proxy - just update fields and is_new
    frm.fields = options.getFields()
    frm.is_new = options.isNew()

    const result = await executeClientScripts(doctype, event, frm, grunt, changedField)

    // Apply overrides from scripts to reactive state
    Object.assign(displayOverrides, frm._display)
    Object.assign(reqdOverrides, frm._reqd)
    for (const [fieldname, overrideProps] of Object.entries(frm._df_props)) {
      dfPropOverrides[fieldname] = { ...dfPropOverrides[fieldname], ...overrideProps }
    }
    if (frm._sidebar_hidden !== undefined) sidebarHidden.value = frm._sidebar_hidden

    return result
  }

  /**
   * Resolve script-registered link filters for a field.
   * Called by Link.vue via injected context.
   *
   * @param fieldname  The Link field's fieldname
   * @param doc        Current document values
   * @returns          Flat filters dict, e.g. `{ status: 'Active' }`
   */
  function getLinkFilters(
    fieldname: string,
    doc: Record<string, unknown>,
  ): Record<string, string | string[]> {
    const fn = frm._queries[fieldname]
    if (!fn) return {}
    try {
      const result = fn(doc)
      // Support both `{ filters: {...} }` and bare `{...}`
      if (result && typeof result === 'object' && 'filters' in result) {
        return (result as { filters: Record<string, string | string[]> }).filters ?? {}
      }
      return result as Record<string, string | string[]>
    } catch {
      return {}
    }
  }

  function setTableSelection(fieldname: string, rowNames: string[]) {
    frm._selected_rows[fieldname] = [...new Set(rowNames.filter(Boolean))]
  }

  return {
    actions,
    frm,
    displayOverrides,
    reqdOverrides,
    dfPropOverrides,
    sidebarHidden,
    runEvent,
    getLinkFilters,
    setTableSelection,
  }
}
