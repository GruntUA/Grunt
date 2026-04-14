import { shallowReactive } from 'vue'
import type { DocField, DocTypeStatusConfig, ActiveFilter } from '@/types'
import type { ListColumn } from '@/core/composables/useListColumns'

/** Data passed to every exporter at export time */
export interface ExportContext {
  doctypeName: string
  doctypeLabel: string
  /** Current page rows — use getAll() to fetch everything */
  rows: Record<string, unknown>[]
  columns: ListColumn[]
  fields: DocField[]
  filters: ActiveFilter[]
  statusConfig: DocTypeStatusConfig | null
  total: number
  /** Field to group rows by (mirrors list view grouping, null = no grouping) */
  groupBy: string | null
  /** Fetches all matching records respecting current filters, search & sort */
  getAll: () => Promise<Record<string, unknown>[]>
}

/** A registered exporter — add your own with registerExporter() */
export interface Exporter {
  id: string
  label: string
  /** Optional lucide icon name (reserved for future UI use) */
  icon?: string
  export: (ctx: ExportContext) => void | Promise<void>
}

// Reactive so the UI automatically updates when exporters are registered after init
const _registry = shallowReactive<Exporter[]>([])

export function registerExporter(exp: Exporter): void {
  const idx = _registry.findIndex(e => e.id === exp.id)
  if (idx !== -1) _registry[idx] = exp
  else _registry.push(exp)
}

/** Returns the live reactive array — safe to use in templates / computed */
export function getExporters(): Exporter[] {
  return _registry
}
