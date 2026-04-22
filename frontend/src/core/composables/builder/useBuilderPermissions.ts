import type { Ref } from 'vue'
import type { DocType, DocTypePermission } from '@/types'

interface UseBuilderPermissionsParams {
  doctype: Ref<DocType | null>
  isDirty: Ref<boolean>
}

export function useBuilderPermissions({ doctype, isDirty }: UseBuilderPermissionsParams) {
  function addPermission(role: string) {
    if (!doctype.value) return
    const perms = [...(doctype.value.permissions ?? [])]
    perms.push({ role, read: true })
    doctype.value = { ...doctype.value, permissions: perms }
    isDirty.value = true
  }

  function updatePermission(index: number, patch: Partial<DocTypePermission>) {
    if (!doctype.value?.permissions) return
    const perms = [...doctype.value.permissions]
    perms[index] = { ...perms[index], ...patch }
    doctype.value = { ...doctype.value, permissions: perms }
    isDirty.value = true
  }

  function removePermission(index: number) {
    if (!doctype.value?.permissions) return
    const perms = [...doctype.value.permissions]
    perms.splice(index, 1)
    doctype.value = { ...doctype.value, permissions: perms }
    isDirty.value = true
  }

  return {
    addPermission,
    updatePermission,
    removePermission,
  }
}
