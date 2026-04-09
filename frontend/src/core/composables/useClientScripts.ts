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
 *   // Render scripts.buttons in template
 */

import { ref, reactive } from 'vue'
import { useDialog } from '@/core/composables/useDialog'
import { toast } from 'vue-sonner'
import {
  createFormProxy,
  createGruntProxy,
  executeClientScripts,
  type FormProxy,
  type GruntProxy,
  type ClientScriptEvent,
  type ScriptButton,
} from '@/core/scripting/executor'

export interface UseClientScriptsOptions {
  getDoc: () => Record<string, unknown>
  getFields: () => Record<string, unknown>[]
  isNew: () => boolean
  setValue: (field: string, value: unknown) => void
  refreshField?: (field: string) => void
  save: () => Promise<void>
}

export function useClientScripts(doctype: string, options: UseClientScriptsOptions) {
  const buttons = ref<ScriptButton[]>([])
  const displayOverrides = reactive<Record<string, boolean>>({})
  const reqdOverrides = reactive<Record<string, boolean>>({})
  const dfPropOverrides = reactive<Record<string, Record<string, unknown>>>({})

  const dialog = useDialog()

  let gruntProxy: GruntProxy | null = null

  // Live proxy for doc — always reads current form values
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

  // Single persistent FormProxy — buttons and other closures keep a stable reference
  const frm: FormProxy = createFormProxy(
    doctype,
    liveDoc,
    options.getFields(),
    {
      setValue: (field, value) => {
        options.setValue(field, value)
      },
      refreshField: options.refreshField,
      addButton: (label, action, opts) => {
        if (!buttons.value.some(b => b.label === label)) {
          buttons.value.push({ label, action, variant: opts?.variant })
        }
      },
      save: options.save,
    },
    options.isNew(),
  )

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
        showAlert: (msg, type) => {
          if (type === 'error') toast.error(msg)
          else if (type === 'success') toast.success(msg)
          else if (type === 'warning') toast.warning(msg)
          else toast.info(msg)
        },
      })
    }
    return gruntProxy
  }

  /**
   * Run a client script event. Returns false if validate returns false.
   */
  async function runEvent(event: ClientScriptEvent, changedField?: string): Promise<boolean> {
    const grunt = ensureGrunt()

    // doc is live via Proxy — just update fields and is_new
    frm.fields = options.getFields()
    frm.is_new = options.isNew()

    const result = await executeClientScripts(doctype, event, frm, grunt, changedField)

    // Apply overrides from scripts to reactive state
    Object.assign(displayOverrides, frm._display)
    Object.assign(reqdOverrides, frm._reqd)
    for (const [fieldname, overrideProps] of Object.entries(frm._df_props)) {
      dfPropOverrides[fieldname] = { ...dfPropOverrides[fieldname], ...overrideProps }
    }

    return result
  }

  return {
    buttons,
    displayOverrides,
    reqdOverrides,
    dfPropOverrides,
    runEvent,
  }
}
