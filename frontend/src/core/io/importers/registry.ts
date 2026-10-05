import { shallowReactive } from 'vue'
import type { DocField } from '@/types'

/** Data available to every importer */
export interface ImportContext {
  doctypeName: string
  doctypeLabel: string
  fields: DocField[]
}

/** A registered importer */
export interface Importer {
  id: string
  label: string
  icon?: string
  /** Called when the user picks this importer from the UI */
  import: (ctx: ImportContext) => void | Promise<void>
}

const _registry = shallowReactive<Importer[]>([])

export function registerImporter(imp: Importer): void {
  const idx = _registry.findIndex(i => i.id === imp.id)
  if (idx !== -1) _registry[idx] = imp
  else _registry.push(imp)
}

/** Returns the live reactive array - safe to use in templates / computed */
export function getImporters(): Importer[] {
  return _registry
}
