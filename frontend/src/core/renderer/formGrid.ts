/**
 * Widths in a form, in twelfths (`DocField.columns`, 12 = not set):
 *
 * - on a `Column` field - the column's share of its section's width
 *   (`8` + `4` → two thirds and a third);
 * - on any other field - its width inside its column, so narrow fields sit
 *   side by side (`6` + `6`, `4` + `4` + `4`) and wrap like words.
 *
 * Both fall back to full width when there is no room: columns stack by the
 * section's width, fields by their column's (container queries).
 */
import type { DocField } from '@/types'

const FULL = 12

/** Column counts → the section width from which they stand side by side. */
const SECTION_GRID_CLASS: Record<number, string> = {
  2: '@lg:grid-cols-2',
  3: '@lg:grid-cols-2 @3xl:grid-cols-3',
  4: '@lg:grid-cols-2 @4xl:grid-cols-4',
}

// Columns with their own widths have no in-between stage: one column, then all.
const SECTION_TEMPLATE_CLASS: Record<number, string> = {
  2: '@lg:grid-cols-(--form-cols)',
  3: '@3xl:grid-cols-(--form-cols)',
  4: '@4xl:grid-cols-(--form-cols)',
}

// Spelled out for Tailwind's scanner.
const SPAN_CLASS: Record<number, string> = {
  1: '@sm:col-span-1',
  2: '@sm:col-span-2',
  3: '@sm:col-span-3',
  4: '@sm:col-span-4',
  5: '@sm:col-span-5',
  6: '@sm:col-span-6',
  7: '@sm:col-span-7',
  8: '@sm:col-span-8',
  9: '@sm:col-span-9',
  10: '@sm:col-span-10',
  11: '@sm:col-span-11',
  12: '@sm:col-span-12',
}

/** `columns` as a whole number of twelfths, 1-12 (anything else - full width). */
export function twelfths(value: unknown): number {
  const n = Math.trunc(Number(value))
  return Number.isFinite(n) && n >= 1 && n <= FULL ? n : FULL
}

/**
 * `grid-template-columns` for a section's columns, or null when none sets a
 * width (equal columns). Columns without a width share what the others leave.
 */
export function columnTemplate(widths: number[] | undefined, count: number): string | null {
  if (count < 2) return null
  const set = Array.from({ length: count }, (_, i) => twelfths(widths?.[i]))
  if (set.every((w) => w === FULL)) return null
  const unset = set.filter((w) => w === FULL).length
  const taken = set.reduce((sum, w) => (w === FULL ? sum : sum + w), 0)
  const share = unset ? Math.max(1, (FULL - taken) / unset) : 0
  return set.map((w) => `minmax(0, ${w === FULL ? share : w}fr)`).join(' ')
}

export function sectionGridClass(widths: number[] | undefined, count: number): string {
  const n = Math.min(count, 4)
  return (columnTemplate(widths, count) ? SECTION_TEMPLATE_CLASS : SECTION_GRID_CLASS)[n] ?? ''
}

/** True when some field of the column is narrower than the column. */
export function hasFieldWidths(fields: DocField[]): boolean {
  return fields.some((f) => twelfths(f.columns) < FULL)
}

export function fieldSpanClass(field: DocField): string {
  return `col-span-12 ${SPAN_CLASS[twelfths(field.columns)]}`
}
