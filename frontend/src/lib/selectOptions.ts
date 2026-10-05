/**
 * Parsing for `Select` / `MultiSelect` field option strings.
 *
 * An option line is either a bare value or `value|IconName`, where `IconName`
 * is a Lucide icon (kebab- or PascalCase) rendered next to the option:
 *
 *   list|LayoutList
 *   kanban|LayoutGrid
 *
 * Only the part before `|` is ever stored or compared - the icon is display-only.
 * A `translatable` field's schema also carries `option_labels` ({value: caption}
 * in the user's language); captions are display-only too.
 */
import type { Component } from 'vue'
import type { DocField } from '@/types'
import { resolveLucideIcon } from '@/lib/lucide'

export type SelectOption = {
  value: string
  /** Caption to show - the translated label, or the value itself. */
  label: string
  /** Lucide icon name given after `|`, or null. */
  icon: string | null
}

/** Parse a DocField `options` value (newline string or array) into `{ value, icon }`. */
export function parseSelectOptions(
  options: string | string[] | null | undefined,
  labels?: Record<string, string> | null,
): SelectOption[] {
  const raw =
    typeof options === 'string' ? options.split('\n') : Array.isArray(options) ? options : []
  return raw
    .map((line) => String(line).trim())
    .filter(Boolean)
    .map((line) => {
      const bar = line.indexOf('|')
      const value = bar === -1 ? line : line.slice(0, bar).trim()
      const icon = bar === -1 ? null : line.slice(bar + 1).trim() || null
      return { value, label: labels?.[value] ?? value, icon }
    })
}

/** Bare option values only - for surfaces that don't render icons. */
export function parseSelectValues(
  options: string | string[] | null | undefined,
): string[] {
  return parseSelectOptions(options).map((o) => o.value)
}

/** Caption of one stored value of a Select / MultiSelect field. */
export function selectOptionLabel(field: Pick<DocField, 'option_labels'> | null | undefined, value: unknown): string {
  const v = String(value ?? '')
  return field?.option_labels?.[v] ?? v
}

/** Resolve the icon names in parsed options into a name -> component map. */
export async function resolveOptionIcons(
  opts: SelectOption[],
): Promise<Record<string, Component>> {
  const names = [...new Set(opts.map((o) => o.icon).filter((n): n is string => !!n))]
  if (!names.length) return {}
  const entries = await Promise.all(
    names.map(async (n) => [n, await resolveLucideIcon(n)] as const),
  )
  return Object.fromEntries(entries.filter(([, c]) => c) as [string, Component][])
}
