/**
 * Type-change advisory for the DocType «Конструктор».
 *
 * Tells the user, when they change a field's `fieldtype` in the builder, whether
 * the underlying database column will be retyped — or added / dropped — during
 * the next `doctype sync`. Storage class itself is declared per field type in its
 * own manifest.json (see fieldRegistry.ts) rather than mirrored here.
 *
 * This is a UI heads-up only. Nothing here mutates the field: existing values
 * are kept as-is and the authoritative migration still runs on sync.
 */

import { getStorageClass, type StorageClass } from './fieldRegistry'
import i18n from '@/plugins/i18n'

const t = (key: string, params: Record<string, unknown> = {}): string => i18n.global.t(key, params)

export type { StorageClass }

/** Storage class for a field type. Unknown / plugin types are assumed text. */
export function storageClassOf(fieldtype: string): StorageClass {
  return getStorageClass(fieldtype)
}

export type TypeChangeSeverity = 'info' | 'danger'

export interface TypeChangeNote {
  severity: TypeChangeSeverity
  message: string
}

/**
 * Retypes the database can widen losslessly — every existing value survives the
 * implicit cast. Keyed `"<from>-><to>"` on storage class.
 */
const SAFE_WIDENINGS = new Set<string>([
  'int->float',
  'int->text',
  'bool->int',
  'bool->float',
  'bool->text',
  'float->text',
  'date->datetime',
  'date->text',
  'datetime->text',
  'time->text',
])

/**
 * Describe what a `from` → `to` fieldtype change does to already-stored data.
 * Returns `null` when the column is untouched (same storage class, e.g.
 * `Data` ↔ `Text` ↔ `Select`, or `from === to`).
 */
export function describeTypeChange(from: string, to: string): TypeChangeNote | null {
  if (from === to) return null

  const a = storageClassOf(from)
  const b = storageClassOf(to)
  if (a === b) return null

  if (a === 'none' || b === 'none') {
    return {
      severity: 'danger',
      message: t('The new type stores values differently (a separate column or a child table). Existing data of this field is not moved automatically — export it before migrating.'),
    }
  }

  if (SAFE_WIDENINGS.has(`${a}->${b}`)) {
    return {
      severity: 'info',
      message: t('The database column type changes during migration. Existing values are compatible and kept.'),
    }
  }

  return {
    severity: 'danger',
    message: t('The database column type changes during migration. Values that cannot be converted to the new type may be lost — check existing data.'),
  }
}
