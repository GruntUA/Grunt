import { computed, ref, type ComputedRef } from 'vue'
import { roleAllows } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'
import { useDocTypeStore } from '@/stores/doctype'
import type { DocAction, DocTypeAction } from '@/core/permissions'
import type { DocType } from '@/types'

/**
 * Whether the current user's roles grant `action` on `doctype` by its rules -
 * e.g. "may create reports" instead of "is System Manager". Row conditions
 * (`match`) aren't known without a document; the server checks them on save.
 * False until the DocType's schema is loaded (or when it can't be); follows
 * the user's roles when the profile is re-read.
 */
export function useDocTypeAllows(
  doctype: string,
  action: DocAction | DocTypeAction,
): ComputedRef<boolean> {
  const schema = ref<DocType | null>(null)
  const auth = useAuthStore()
  useDocTypeStore()
    .get(doctype)
    .then((dt) => {
      schema.value = dt
    })
    .catch(() => {
      schema.value = null
    })
  return computed(() => roleAllows(schema.value, action, auth.user?.roles ?? []))
}
