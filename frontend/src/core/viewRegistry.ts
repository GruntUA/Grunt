/**
 * View Registry
 *
 * Single source of truth for every list-view type in the system.
 * Built-in views (list, kanban, calendar, tree, gallery, map) are registered
 * via their own index.ts files inside src/components/views/{type}/.
 *
 * External apps register custom views the same way — create a directory,
 * add an index.ts that calls registerView(), and the registry picks it up
 * automatically via import.meta.glob.
 *
 * Usage from a custom view (e.g. my-app/views/timeline/index.ts):
 *
 *   // IMPORTANT: use `import type` only — never import runtime values from
 *   // viewRegistry in an index.ts, to avoid circular-initialization errors.
 *
 *   import { Clock } from '@lucide/vue'
 *   import type { ViewDefinition } from '@/core/viewRegistry'
 *   import type { DocType, DocField } from '@/types'
 *
 *   const def: ViewDefinition = {
 *     type: 'timeline',
 *     label: 'Таймлайн',
 *     icon: Clock,
 *     order: 10,
 *     resolveField: (dt: DocType): DocField | null =>
 *       dt.fields.find(f => f.fieldtype === 'Datetime' && f.in_list_view) ?? null,
 *     component: () => import('./TimelineView.vue').then(m => m.default),
 *     mountProps: (ctx) => ({
 *       doctype: ctx.dt,
 *       dateField: ctx.resolvedField?.fieldname ?? '',
 *       workspace: ctx.workspace,
 *     }),
 *   }
 *
 *   export default def
 *
 * After the file is saved, the view button appears automatically in DocTypeToolbar
 * and the component is rendered by ListViewRouter.
 */

import type { Component } from 'vue'
import type { DocType, DocField, ActiveFilter, QuickFilter, ScriptMenuItem } from '@/types'
import type { ListColumn } from '@/core/composables/useListColumns'
import type { GroupedRowBucket } from '@/core/composables/useGrouping'

// ── Shared sub-types ──────────────────────────────────────────────────────────

export interface SelectionState {
  selectedIds: string[]
  allSelected: boolean
  isSelected: (id: string) => boolean
  toggle: (id: string) => void
  toggleAll: (ids: string[]) => void
}

/** Typed wrapper around ListViewRouter's emit, passed into mountProps/mountEvents. */
export interface ViewEmit {
  sort(key: string): void
  rowClick(row: Record<string, unknown>): void
  inlineUpdate(rowId: string, field: string, value: string): void
  delete(): void
  fastDelete(): void
  clear(): void
  selectAll(): void
  update(field: string, value: unknown): void
  toggleGroup(key: string): void
  page(page: number): void
  registerMenuItems(items: ScriptMenuItem[]): void
  unregisterMenuItems(items: ScriptMenuItem[]): void
  updateQuickFilterValues(val: Record<string, string>): void
  updateActiveFilters(val: ActiveFilter[]): void
}

/**
 * Full context passed to each view's mountProps / mountEvents functions.
 * It is the superset of everything currently available in ListViewRouter.
 * Each view picks only what it needs.
 */
export interface ViewContext {
  /** The active DocType definition (null while loading). */
  dt: DocType | null
  workspace: string
  doctype: string
  // Data provided by the parent list query
  rows: Record<string, unknown>[]
  fields: DocField[]
  columns: ListColumn[]
  meta?: { page: number; pages: number; total: number }
  isLoading: boolean
  hasData: boolean
  // Selection
  selectionCount: number
  selection: SelectionState
  // Display helpers
  imageField?: string
  // Grouping
  groupBy: string | null
  groupedRows: GroupedRowBucket[] | null
  collapsedGroups: Set<string>
  groupByField: DocField | null
  // Sorting
  sortKey: string | null
  sortOrder: 'asc' | 'desc'
  // Infinite scroll / pagination
  fetchNextPage?: () => void
  hasNextPage?: boolean
  isFetchingNextPage?: boolean
  // Filters
  search?: string
  activeFilters: ActiveFilter[]
  quickFilterDefs: QuickFilter[]
  quickFilterValues: Record<string, string>
  /**
   * Result of calling the active view's resolveField(dt).
   * Pre-computed once by ListViewRouter so mountProps can use it without a
   * second lookup.  Null for views that have no resolveField (list, gallery).
   */
  resolvedField: DocField | null
  /** Typed wrappers around ListViewRouter's emit function. */
  emit: ViewEmit
  /** Whether the current user is a superadmin (for privileged actions like fast delete). */
  isSuperadmin?: boolean
  /**
   * Bumped by the header's Refresh button. Views that fetch their own data
   * (tree, calendar, kanban — anything outside the shared `['documents', doctype]`
   * query) should watch this and refetch; views on the shared query already
   * refetch automatically when it's invalidated and don't need to read this.
   */
  refreshKey: number
}

// ── ViewDefinition ─────────────────────────────────────────────────────────────

export interface ViewDefinition {
  /** Unique identifier — used as the viewMode string (e.g. 'kanban'). */
  type: string
  /** Tooltip shown on the toolbar button. */
  label: string
  /** Lucide icon component (imported directly, not a string). */
  icon: Component
  /** Position in the toolbar — lower numbers appear first. */
  order: number
  /** Builder-only entries can opt out of toolbar and route availability. */
  showInToolbar?: boolean
  /**
   * Detects the field that enables this view for a given DocType.
   * The toolbar button is hidden when this returns null.
   * Omit entirely for views that are always available (list, gallery).
   */
  resolveField?(dt: DocType): DocField | null
  /** Async loader for the view's root Vue component. */
  component(): Promise<Component>
  /**
   * Maps ViewContext → the props object bound to the component via v-bind.
   * Called reactively on each render by ListViewRouter.
   */
  mountProps?(ctx: ViewContext): Record<string, unknown>
  /**
   * Maps ViewContext → event handlers bound to the component via v-on.
   * Keys use Vue's camelCase onXxx convention (e.g. 'onRowClick').
   * For update:* events keep the colon: 'onUpdate:quickFilterValues'.
   */
  mountEvents?(ctx: ViewContext): Record<string, (...args: unknown[]) => void>
  /**
   * Async loader for the view's toolbar controls component.
   * Rendered by DocTypeToolbar in the controls zone (between filters and view switcher).
   * Omit if the view needs no custom toolbar controls.
   */
  toolbarControls?: () => Promise<Component>
  /**
   * Maps ToolbarContext → props for the toolbarControls component.
   * ctx.extras contains view-specific data provided by DocTypeList.
   */
  mountToolbarProps?: (ctx: ToolbarContext) => Record<string, unknown>
  /**
   * Maps ToolbarContext → event handlers for the toolbarControls component.
   * Keys use Vue's camelCase onXxx convention.
   */
  mountToolbarEvents?: (ctx: ToolbarContext) => Record<string, (...args: unknown[]) => void>
}

// ── Toolbar types ─────────────────────────────────────────────────────────────

/** Typed wrappers around DocTypeToolbar's emit, passed into mountToolbarProps/Events. */
export interface ToolbarEmit {
  updateViewMode(val: string): void
  updateInlineSearch(val: string): void
  updateActiveFilters(val: ActiveFilter[]): void
  updateQuickFilterValues(val: Record<string, string>): void
  /** Emitted by view toolbar controls that need group-by (e.g. list). */
  updateGroupBy(val: string | null): void
  /** Emitted by view toolbar controls that need sorting (e.g. list). */
  sort(key: string): void
}

/**
 * Context passed to a view's mountToolbarProps / mountToolbarEvents.
 * Contains toolbar-level state plus an opaque extras bag for view-specific data
 * that DocTypeList provides (columns, groupableFields, etc.).
 */
export interface ToolbarContext {
  dt: DocType | null
  doctype: string
  viewMode: string
  inlineSearch: string
  activeFilters: ActiveFilter[]
  quickFilterDefs: QuickFilter[]
  quickFilterValues: Record<string, string>
  /**
   * Opaque view-specific data injected by DocTypeList.
   * Each view's mountToolbarProps casts the values it needs.
   */
  extras: Record<string, unknown>
  emit: ToolbarEmit
}

// ── Internal registry ─────────────────────────────────────────────────────────

const _registry = new Map<string, ViewDefinition>()

// ── Public API ────────────────────────────────────────────────────────────────

/** Register a view. Must be called before the Vue app mounts. */
export function registerView(def: ViewDefinition): void {
  _registry.set(def.type, def)
}

/** Retrieve a view definition by type string. */
export function getViewDef(type: string): ViewDefinition | undefined {
  return _registry.get(type)
}

/** All registered views sorted by order. Used by DocTypeToolbar. */
export function getRegisteredViews(): ViewDefinition[] {
  return [..._registry.values()]
    .filter((def) => def.showInToolbar !== false)
    .sort((a, b) => a.order - b.order)
}

/**
 * View types available for a given DocType.
 * Views without resolveField are always included.
 * Views whose resolveField returns null are excluded.
 * Used by DocTypeList to compute the validViews set for route sync.
 */
export function getAvailableViewTypes(dt: DocType | null): string[] {
  return getRegisteredViews()
    .filter((def) => {
      if (!def.resolveField) return true
      if (!dt) return false
      return def.resolveField(dt) !== null
    })
    .map((def) => def.type)
}

/**
 * Resolves the required field for a given view type and DocType.
 * Returns null when the view has no resolveField or when dt is null.
 */
export function resolveViewField(type: string, dt: DocType | null): DocField | null {
  if (!dt) return null
  return _registry.get(type)?.resolveField?.(dt) ?? null
}

// ── Auto-discovery ────────────────────────────────────────────────────────────
// Each src/components/views/*/index.ts exports a ViewDefinition as `default`.
// The registry eagerly imports them and registers each definition.
// index.ts files must NOT import from viewRegistry at runtime (only `import type`)
// to avoid the circular-initialization ReferenceError.
const _viewModules = import.meta.glob<{ default: ViewDefinition }>(
  '@/components/views/*/index.ts',
  { eager: true },
)
for (const mod of Object.values(_viewModules)) {
  if (mod?.default) registerView(mod.default)
}
