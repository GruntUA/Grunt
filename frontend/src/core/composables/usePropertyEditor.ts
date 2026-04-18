import { inject, type InjectionKey, type Ref } from 'vue'
import type { DocField } from '@/types'

export const PROPERTY_FIELD_KEY: InjectionKey<Ref<DocField>> = Symbol('propertyField')
export const PROPERTY_UPDATE_KEY: InjectionKey<(key: string, val: unknown) => void> = Symbol('propertyUpdate')

/** Used inside property section components to access the selected field and updater. */
export function usePropertyEditor() {
  const field = inject(PROPERTY_FIELD_KEY)!
  const updateField = inject(PROPERTY_UPDATE_KEY)!
  return { field, updateField }
}
