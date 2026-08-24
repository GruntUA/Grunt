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

import { ref, reactive, watch } from 'vue'
import type { Ref } from 'vue'
import { useRouter } from 'vue-router'
import { useDialog } from '@/core/composables/useDialog'
import { useToast } from '@/core/composables/useToast'
import {
  createFormProxy,
  createGruntProxy,
  dispatchMessageToProxy,
  executeClientScripts,
  type FormScriptMenuItemHandle,
  type FormProxy,
  type GruntProxy,
  type ClientScriptEvent,
  type ScriptButton,
  type ScriptMenuItem,
  type ScriptButtonOptions,
} from '@/core/scripting/executor'

export interface UseClientScriptsOptions {
  getDoc: () => Record<string, unknown>
  getFields: () => Record<string, unknown>[]
  isNew: () => boolean
  setValue: (field: string, value: unknown) => void
  refreshField?: (field: string) => void
  reload: () => Promise<void>
  save: () => Promise<void>
  markClean?: () => void
  /** Reactive ref to the latest WebSocket message on the document channel */
  lastMessage?: Ref<unknown>
}

export function useClientScripts(doctype: string, options: UseClientScriptsOptions) {
    const SEVERITY_MAP: Record<string, string | undefined> = {
  primary: 'default',
      default: undefined,
      secondary: 'secondary',
      success: 'success',
      info: 'info',
      warn: 'warning',
      warning: 'warning',
      danger: 'destructive',
      error: 'destructive',
      contrast: 'secondary',
      gray: 'secondary',
      blue: 'info',
      green: 'success',
      yellow: 'warning',
      orange: 'warning',
      red: 'destructive',
    }

    const COLOR_CLASS_MAP: Record<string, string> = {
      purple: 'border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-300',
      pink: 'border-pink-500/30 bg-pink-500/10 text-pink-700 dark:text-pink-300',
      teal: 'border-teal-500/30 bg-teal-500/10 text-teal-700 dark:text-teal-300',
    }

    function normalizeButtonStyle(opts?: ScriptButtonOptions) {
      const tone = String(opts?.color ?? opts?.variant ?? '').trim().toLowerCase()
      return {
        severity: tone ? SEVERITY_MAP[tone] : undefined,
        className: tone ? (COLOR_CLASS_MAP[tone] ?? '') : '',
        icon: opts?.icon,
        group: opts?.group,
      }
    }

  function buttonKey(label: string, group?: string | null) {
    return `${String(group ?? '').trim()}::${label}`
  }

  function menuKey(label: string) {
    return label.trim().toLowerCase()
  }

  function applyButtonType(btn: ScriptButton, buttonType: string): ScriptButton {
    const style = normalizeButtonStyle({ color: buttonType })
    return {
      ...btn,
      severity: style.severity,
      className: style.className,
    }
  }

  const dialog = useDialog()
  const toast = useToast()
  const router = useRouter()
  const buttons = ref<ScriptButton[]>([])
  const menuItems = ref<ScriptMenuItem[]>([])
  const displayOverrides = reactive<Record<string, boolean>>({})
  const reqdOverrides = reactive<Record<string, boolean>>({})
  const dfPropOverrides = reactive<Record<string, Record<string, unknown>>>({})

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
        const style = normalizeButtonStyle(opts)
        const key = buttonKey(label, style.group)
        const idx = buttons.value.findIndex(b => buttonKey(b.label, b.group) === key)
        const next: ScriptButton = {
          label,
          action,
          severity: style.severity,
          className: style.className,
          icon: style.icon,
          group: style.group,
        }
        if (idx >= 0) {
          buttons.value[idx] = next
        } else {
          buttons.value.push(next)
        }
      },
      addMenuItem: (label, action, options): FormScriptMenuItemHandle => {
        const key = menuKey(label)
        const idx = menuItems.value.findIndex((i) => menuKey(i.label) === key)
        const next: ScriptMenuItem = {
          label,
          action,
          icon: options?.icon,
          separator_before: options?.separator_before,
        }

        if (idx >= 0) {
          menuItems.value[idx] = next
        } else {
          menuItems.value.push(next)
        }

        return {
          update: (updates: { label?: string; icon?: string; separator_before?: boolean }) => {
            const i = menuItems.value.findIndex((x) => menuKey(x.label) === key)
            if (i < 0) return
            menuItems.value[i] = {
              ...menuItems.value[i],
              ...updates,
            }
          },
          remove: () => {
            const i = menuItems.value.findIndex((x) => menuKey(x.label) === key)
            if (i !== -1) menuItems.value.splice(i, 1)
          },
        }
      },
      removeButton: (label, group) => {
        const key = buttonKey(label, group)
        buttons.value = buttons.value.filter((b) => buttonKey(b.label, b.group) !== key)
      },
      clearButtons: () => {
        buttons.value = []
        menuItems.value = []
      },
      updateButtonType: (label, group, buttonType) => {
        const key = buttonKey(label, group)
        const idx = buttons.value.findIndex((b) => buttonKey(b.label, b.group) === key)
        if (idx < 0) return
        buttons.value[idx] = applyButtonType(buttons.value[idx], buttonType)
      },
      reload: options.reload,
      save: options.save,
      markClean: options.markClean,
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
        showAlert: (msg: string, type: 'info' | 'success' | 'error' | 'warning' = 'info') => {
          if (type === 'success') toast.success(msg)
          else if (type === 'error') toast.error(msg)
          else if (type === 'warning') toast.warning(msg)
          else toast.info(msg)
        },
        prompt: (labelOrOpts, title) => dialog.prompt(labelOrOpts as any, title),
        form: (opts) => dialog.form(opts as any),
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
    buttons,
    menuItems,
    displayOverrides,
    reqdOverrides,
    dfPropOverrides,
    runEvent,
    getLinkFilters,
    setTableSelection,
  }
}
