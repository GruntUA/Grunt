import { ref } from 'vue'
import type { Ref } from 'vue'
import type { QueryClient } from '@tanstack/vue-query'
import {
  createListViewProxy,
  createGruntProxy,
  executeListSetup,
} from '@/core/scripting/executor'
import type { ScriptButton, ScriptMenuItem } from '@/types'

interface UseListClientScriptsParams {
  doctype: string
  activeFilters: Ref<any[]>
  page: Ref<number>
  queryClient: QueryClient
  dialog: any
  toast: any
}

export function useListClientScripts(params: UseListClientScriptsParams) {
  const listButtons = ref<ScriptButton[]>([])
  const listMenuItems = ref<ScriptMenuItem[]>([])

  async function runListClientSetup() {
    const gruntProxy = createGruntProxy({
      msgprint: (msgOrOpts) =>
        params.dialog.msgprint(
          typeof msgOrOpts === 'string'
            ? msgOrOpts
            : {
                message: msgOrOpts.message,
                title: msgOrOpts.title,
                indicator: msgOrOpts.indicator,
              },
        ),
      confirm: (msg, title) => params.dialog.confirm(msg, title),
      showAlert: (msg, type) => {
        if (type === 'error') params.toast.error(msg)
        else if (type === 'success') params.toast.success(msg)
        else if (type === 'warning') params.toast.warning(msg)
        else params.toast.info(msg)
      },
      prompt: (labelOrOpts, title) => params.dialog.prompt(labelOrOpts, title),
      warn: (title, message, primaryLabel) => params.dialog.confirm(`${title}\n${message}`, primaryLabel),
      form: (opts) => params.dialog.form(opts),
      showProgress: (title, count, total, description) =>
        params.dialog.progress(title, count, total, description),
    })

    const listview = createListViewProxy(params.doctype, {
      addButton(label, action, options) {
        const btn: ScriptButton = { label, action, severity: options?.variant }
        const idx = listButtons.value.push(btn) - 1
        return {
          update(updates) {
            listButtons.value[idx] = { ...listButtons.value[idx], ...updates }
          },
        }
      },
      addMenuItem(label, action, options) {
        const item: ScriptMenuItem = {
          label,
          action,
          separator_before: options?.separator_before,
        }
        const idx = listMenuItems.value.push(item) - 1
        return {
          update(updates) {
            listMenuItems.value[idx] = { ...listMenuItems.value[idx], ...updates }
          },
          remove() {
            listMenuItems.value.splice(idx, 1)
          },
        }
      },
      refresh() {
        params.queryClient.invalidateQueries({ queryKey: ['documents', params.doctype] })
      },
      setFilters(filters) {
        params.activeFilters.value = filters.map((f) => ({
          fieldname: f.fieldname,
          label: f.label ?? f.fieldname,
          fieldtype: f.fieldtype,
          op: f.op,
          value: f.value,
        }))
        params.page.value = 1
      },
    })

    await executeListSetup(params.doctype, listview, gruntProxy)
  }

  return {
    listButtons,
    listMenuItems,
    runListClientSetup,
  }
}
