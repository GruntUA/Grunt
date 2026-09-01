/**
 * Parsing for `Select` / `MultiSelect` field option strings.
 *
 * An option line is either a bare value or `value|IconName`, where `IconName`
 * is a Lucide icon (kebab- or PascalCase) rendered next to the option:
 *
 *   list|LayoutList
 *   kanban|LayoutGrid
 *
 * Only the part before `|` is ever stored or compared — the icon is display-only.
 */
import type { Component } from 'vue'
import { resolveLucideIcon } from '@/lib/lucide'

export interface SelectOption {
  value: string
  /** Lucide icon name given after `|`, or null. */
  icon: string | null
}

/** Parse a DocField `options` value (newline string or array) into `{ value, icon }`. */
export function parseSelectOptions(
  options: string | string[] | null | undefined,
): SelectOption[] {
  const raw =
    typeof options === 'string' ? options.split('\n') : Array.isArray(options) ? options : []
  return raw
    .map((line) => String(line).trim())
    .filter(Boolean)
    .map((line) => {
      const bar = line.indexOf('|')
      return bar === -1
        ? { value: line, icon: null }
        : { value: line.slice(0, bar).trim(), icon: line.slice(bar + 1).trim() || null }
    })
}

/** Bare option values only — for surfaces that don't render icons. */
export function parseSelectValues(
  options: string | string[] | null | undefined,
): string[] {
  return parseSelectOptions(options).map((o) => o.value)
}

/** Resolve the icon names in parsed options into a name → component map. */
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
