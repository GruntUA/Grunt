import { computed, ref, type Ref } from 'vue'
import { onBeforeRouteLeave, type Router } from 'vue-router'

import { useShortcut } from '@/core/composables/useShortcuts'

interface UseFormNavigationParams {
  router: Router
  doctype: string
  workspace?: string
  isDirty: Ref<boolean>
  showDeleteModal: Ref<boolean>
  showVersions: Ref<boolean>
  isQuickEntryOpen: Ref<boolean>
}

export function useFormNavigation(params: UseFormNavigationParams) {
  const showLeaveModal = ref(false)
  const pendingRoute = ref<string | null>(null)
  const allowLeave = ref(false)

  const listPath = computed(() => {
    return params.workspace ? `/${params.workspace}/${params.doctype}` : `/${params.doctype}`
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

    if (params.showVersions.value) {
      params.showVersions.value = false
      return
    }

    goToList()
  }, { preventDefault: true, allowInInput: false })

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
