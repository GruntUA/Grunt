import { ref } from 'vue'
import type { Ref } from 'vue'
import type { QueryClient } from '@tanstack/vue-query'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { createActionRegistry } from '@/core/actions'
import {
  createListViewProxy,
  createGruntProxy,
  executeListSetup,
  executeListQuickFilterOnChange,
  type ListQuickFilterChange,
  type ListViewProxy,
  type ListViewState,
  type GruntProxy,
} from '@/core/scripting/executor'

interface UseListClientScriptsParams {
  doctype: string
  activeFilters: Ref<any[]>
  quickFilterValues: Ref<Record<string, string>>
  setQuickFilterValue: (id: string, value: string) => void
  setQuickFilters: (values: Record<string, string>) => void
  page: Ref<number>
  queryClient: QueryClient
  dialog: any
  toast: any
  /** Live list state behind listview.perm / selected / … */
  state: () => ListViewState
  /** Flows the standard actions (global_list.js) open. */
  ui: {
    newDoc: () => void
    bulkEdit: () => void
    bulkDelete: () => void
    fastDelete: () => void
    exportWith: (exporterId: string) => void
    customizeQuickFilters: () => void
    createReport: () => void
    /** Re-fetch the DocType definition from the server. */
    reloadMeta: () => Promise<void>
    /** After a refresh — views that fetch on their own (tree, calendar…) reload too. */
    refreshed?: () => void
  }
}

export function useListClientScripts(params: UseListClientScriptsParams) {
  const router = useRouter()
  const { t } = useI18n()
  const listviewProxy = ref<ListViewProxy | null>(null)
  const gruntProxy = ref<GruntProxy | null>(null)

  // Every button / menu item / bulk action of the list (core/actions.ts) —
  // filled by global_list.js, the DocType's script and ClientScripts.
  const actions = createActionRegistry<ListViewProxy>(() => listviewProxy.value!, {
    confirm: (message) => params.dialog.confirm(message),
    translate: (label) => t(label),
  })

  async function runListClientSetup() {
    const gp = createGruntProxy({
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
      select: (opts) => params.dialog.select(opts as any),
      showProgress: (title, count, total, description) =>
        params.dialog.progress(title, count, total, description),
      navigateTo: (href, inNewTab) => {
        if (inNewTab) {
          window.open(href, '_blank')
          return
        }
        router.push(href)
      },
    })

    const lv = createListViewProxy(params.doctype, {
      state: params.state,
      async refresh(options) {
        if (options?.meta) await params.ui.reloadMeta()
        await params.queryClient.invalidateQueries({ queryKey: ['documents', params.doctype] })
        params.ui.refreshed?.()
      },
      newDoc: params.ui.newDoc,
      bulkEdit: params.ui.bulkEdit,
      bulkDelete: params.ui.bulkDelete,
      fastDelete: params.ui.fastDelete,
      exportWith: params.ui.exportWith,
      customizeQuickFilters: params.ui.customizeQuickFilters,
      createReport: params.ui.createReport,
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
      setQuickFilterValue(id, value) {
        params.setQuickFilterValue(id, value)
      },
      setQuickFilters(values) {
        params.setQuickFilters(values)
      },
    }, actions)

    listviewProxy.value = lv
    gruntProxy.value = gp
    actions.clear()
    await executeListSetup(params.doctype, lv, gp)
  }

  async function runQuickFilterOnChange(change: ListQuickFilterChange) {
    if (!listviewProxy.value || !gruntProxy.value) return
    await executeListQuickFilterOnChange(
      params.doctype,
      listviewProxy.value,
      gruntProxy.value,
      change,
    )
  }

  return {
    actions,
    runListClientSetup,
    runQuickFilterOnChange,
  }
}
