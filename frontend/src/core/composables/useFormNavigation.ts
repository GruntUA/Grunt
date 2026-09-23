import { computed, ref, type Ref } from 'vue'
import { onBeforeRouteLeave, type Router } from 'vue-router'

import { useShortcut } from '@/core/composables/useShortcuts'
import { docUrl } from '@/core/workspaceUrl'

interface UseFormNavigationParams {
  router: Router
  doctype: string
  workspace?: string
  isDirty: Ref<boolean>
  showDeleteModal: Ref<boolean>
  isQuickEntryOpen: Ref<boolean>
}

export function useFormNavigation(params: UseFormNavigationParams) {
  const showLeaveModal = ref(false)
  const pendingRoute = ref<string | null>(null)
  const allowLeave = ref(false)

  const listPath = computed(() => {
    return docUrl(params.doctype, null, params.workspace)
  })

  function markAllowLeave() {
    allowLeave.value = true
  }

  function goToList() {
    markAllowLeave()
    params.router.push(listPath.value)
  }

  function confirmLeave() {
    showLeaveModal.value = false
    markAllowLeave()

    if (pendingRoute.value) {
      params.router.push(pendingRoute.value)
      pendingRoute.value = null
    }
  }

  function cancelLeave() {
    showLeaveModal.value = false
  }

  useShortcut(['escape'], () => {
    if (params.showDeleteModal.value || showLeaveModal.value || params.isQuickEntryOpen.value) return
    // Escape that closes a menu / popover / select / sheet is not "leave the form".
    // reka-ui handles it on `document` first; its layer is still in the DOM here.
    if (document.querySelector('[data-dismissable-layer]')) return

    goToList()
    // No preventDefault: reka-ui's own Escape handler (also on window, registered
    // later) skips dismissing a menu when the event is already defaultPrevented.
  }, { allowInInput: false })

  onBeforeRouteLeave((to) => {
    if (allowLeave.value || !params.isDirty.value) {
      return true
    }

    showLeaveModal.value = true
    pendingRoute.value = to.fullPath
    return false
  })

  return {
    showLeaveModal,
    markAllowLeave,
    confirmLeave,
    cancelLeave,
    goToList,
  }
}
