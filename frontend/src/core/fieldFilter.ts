import type { DocField } from '@/types'
import { getLayoutTypeSet } from '@/core/fieldRegistry'

/**
 * Keep only the given leaf fields plus whatever Tab/Section/Column wrappers
 * still contain at least one of them, preserving the original order — used
 * to carve a small dialog form (quick entry, a workflow action prompt) out
 * of a DocType's full field list without losing its layout scaffolding.
 */
export function filterFieldsByName(fields: DocField[], names: Set<string>): DocField[] {
  const LAYOUT_TYPES = getLayoutTypeSet()

  function hasVisibleIn(start: number, end: number): boolean {
    for (let i = start; i < end; i++) {
      if (!LAYOUT_TYPES.has(fields[i].fieldtype) && names.has(fields[i].fieldname)) return true
    }
    return false
  }

  function scopeEnd(i: number, type: string): number {
    for (let j = i + 1; j < fields.length; j++) {
      if (fields[j].fieldtype === type) return j
      if (type !== 'Tab' && fields[j].fieldtype === 'Tab') return j
      if (type === 'Column' && fields[j].fieldtype === 'Section') return j
    }
    return fields.length
  }

  const result: DocField[] = []
  for (let i = 0; i < fields.length; i++) {
    const f = fields[i]
    if (LAYOUT_TYPES.has(f.fieldtype)) {
      if (hasVisibleIn(i + 1, scopeEnd(i, f.fieldtype))) result.push(f)
    } else if (names.has(f.fieldname)) {
      result.push(f)
    }
  }
  return result
}
