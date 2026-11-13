import { ref, type Ref } from 'vue'
import { roleAllows } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'
import { useDocTypeStore } from '@/stores/doctype'
import type { DocAction, DocTypeAction } from '@/core/permissions'

/**
 * Whether the current user's roles grant `action` on `doctype` by its rules -
 * e.g. "may create reports" instead of "is System Manager". Row conditions
 * (`match`) aren't known without a document; the server checks them on save.
 * False until the DocType's schema is loaded (or when it can't be).
 */
export function useDocTypeAllows(doctype: string, action: DocAction | DocTypeAction): Ref<boolean> {
  const allowed = ref(false)
  const auth = useAuthStore()
  useDocTypeStore()
    .get(doctype)
    .then((dt) => {
      allowed.value = roleAllows(dt, action, auth.user?.roles ?? [])
    })
    .catch(() => {
      allowed.value = false
    })
  return allowed
}
