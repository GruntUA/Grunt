/**
 * Action registry - every button and menu item of a form or a list.
 *
 * Nothing in the form/list header is hard-coded: the framework's
 * `global_form.js` / `global_list.js` register the standard actions (Save,
 * Delete, Print, «Додати», bulk edit…) for every DocType, the DocType's own
 * `.js` adds its actions and changes or removes the standard ones by `id`,
 * and a ClientScript from the database has the last word.
 *
 * ```js
 * frm.actions.add({
 *   id: 'approve',
 *   label: 'Погодити',
 *   placement: 'toolbar',          // primary | toolbar | menu | bulk (lists)
 *   icon: 'check',
 *   visible: (frm) => frm.perm.write && frm.doc.status === 'Draft',
 *   action: (frm) => frm.set_value('status', 'Approved'),
 * })
 * frm.actions.update('save', { label: 'Провести' })
 * frm.actions.remove('duplicate')
 * ```
 *
 * `visible` / `enabled` / `busy` / a function `label` are re-evaluated
 * reactively - they may read `frm.doc`, `frm.perm`, `frm.is_dirty`, … .
 */
import { computed, shallowRef, triggerRef, type ComputedRef } from 'vue'

export type ActionPlacement = 'primary' | 'toolbar' | 'menu' | 'bulk' | 'workflow'

export interface ActionDef<C = any> {
  /** Stable id - `update` / `remove` / a later `add` with the same id address it. */
  id: string
  label: string | ((ctx: C) => string)
  /** primary - the main button (right-most); toolbar - buttons; menu - the «⋯» menu;
   *  workflow - the workflow bar (transitions); bulk - list selection bar. Default: toolbar. */
  placement?: ActionPlacement
  /** Lucide icon name (kebab-case), e.g. `save`, `trash-2`. */
  icon?: string
  /** Toolbar: an icon-only button, the label becomes its tooltip. */
  icon_only?: boolean
  /** Toolbar: buttons of one group form a split button. Menu: a section (separated from the others). */
  group?: string
  /** Sort key, lower first. Standard actions use hundreds, so yours fit in between. Default 500. */
  order?: number
  /** default | outline | secondary | ghost | destructive | success | warning | info, or a colour name. */
  variant?: string
  /** Keyboard shortcut, e.g. `Mod+S` - ⌘ on macOS, Ctrl elsewhere (core/shortcuts.ts). Works while typing in a field. */
  shortcut?: string
  visible?: (ctx: C) => boolean
  enabled?: (ctx: C) => boolean
  /** Show a spinner (e.g. while saving). */
  busy?: (ctx: C) => boolean
  /** Ask before running. */
  confirm?: string | ((ctx: C) => string)
  action: (ctx: C) => unknown
}

/** An action ready to render. */
export interface ResolvedAction {
  id: string
  label: string
  placement: ActionPlacement
  icon?: string
  iconOnly: boolean
  group: string
  variant?: string
  shortcut?: string
  disabled: boolean
  busy: boolean
  run: () => Promise<void>
}

export interface ActionsApi<C = any> {
  add: (def: ActionDef<C>) => void
  update: (id: string, patch: Partial<Omit<ActionDef<C>, 'id'>>) => void
  remove: (id: string) => void
  get: (id: string) => ActionDef<C> | undefined
  /** Every registered action (e.g. to drop a family: `list().filter(a => a.id.startsWith('workflow:'))`). */
  list: () => ActionDef<C>[]
  /** Run an action by id (respects `enabled` and `confirm`). */
  run: (id: string) => Promise<void>
}

export interface ActionRegistry<C = any> extends ActionsApi<C> {
  /** Reactive, sorted actions of one placement. */
  resolved: (placement: ActionPlacement) => ComputedRef<ResolvedAction[]>
  /** Visible + enabled actions that have a shortcut. */
  withShortcut: () => ResolvedAction[]
  clear: () => void
}

const DEFAULT_ORDER = 500

export function createActionRegistry<C>(
  getCtx: () => C,
  deps: { confirm: (message: string) => Promise<boolean>; translate?: (label: string) => string },
): ActionRegistry<C> {
  // Insertion order breaks ties in `order`; a re-`add` keeps the original slot.
  const defs = shallowRef(new Map<string, ActionDef<C>>())
  const t = deps.translate ?? ((s: string) => s)

  /** `fn(ctx)`; `unset` when there is no fn, `failed` when it throws (a broken
   *  predicate hides/disables its action instead of breaking the header). */
  function safe<T>(fn: ((ctx: C) => T) | undefined, unset: T, failed: T = unset): T {
    if (!fn) return unset
    try {
      return fn(getCtx())
    } catch (err) {
      console.warn('[actions] predicate failed:', err)
      return failed
    }
  }

  async function runDef(def: ActionDef<C>) {
    if (!safe(def.enabled, true, false)) return
    const message = typeof def.confirm === 'function' ? safe(def.confirm, '') : def.confirm
    if (message && !(await deps.confirm(t(message)))) return
    await def.action(getCtx())
  }

  function resolve(def: ActionDef<C>): ResolvedAction {
    const label = typeof def.label === 'function' ? safe(def.label, def.id) : def.label
    return {
      id: def.id,
      label: t(label),
      placement: def.placement ?? 'toolbar',
      icon: def.icon,
      iconOnly: !!def.icon_only,
      group: def.group ?? '',
      variant: def.variant,
      shortcut: def.shortcut,
      disabled: !safe(def.enabled, true, false),
      busy: safe(def.busy, false),
      run: () => runDef(def),
    }
  }

  function visibleDefs(): ActionDef<C>[] {
    const all = [...defs.value.values()]
    return all
      .map((def, index) => ({ def, index }))
      .filter(({ def }) => safe(def.visible, true, false))
      .sort((a, b) => (a.def.order ?? DEFAULT_ORDER) - (b.def.order ?? DEFAULT_ORDER) || a.index - b.index)
      .map(({ def }) => def)
  }

  const api: ActionRegistry<C> = {
    add(def) {
      if (!def?.id) throw new Error('actions.add: `id` is required')
      defs.value.set(def.id, { ...def })
      triggerRef(defs)
    },
    update(id, patch) {
      const current = defs.value.get(id)
      if (!current) return
      defs.value.set(id, { ...current, ...patch })
      triggerRef(defs)
    },
    remove(id) {
      if (defs.value.delete(id)) triggerRef(defs)
    },
    get(id) {
      return defs.value.get(id)
    },
    list() {
      return [...defs.value.values()]
    },
    async run(id) {
      const def = defs.value.get(id)
      if (def && safe(def.visible, true, false)) await runDef(def)
    },
    resolved(placement) {
      return computed(() =>
        visibleDefs()
          .filter((def) => (def.placement ?? 'toolbar') === placement)
          .map(resolve),
      )
    },
    withShortcut() {
      return visibleDefs().filter((def) => def.shortcut).map(resolve).filter((a) => !a.disabled)
    },
    clear() {
      defs.value.clear()
      triggerRef(defs)
    },
  }
  return api
}

/** Button look for an action `variant`: a shadcn Button variant, or a tone/colour
 *  drawn as an outline button with coloured classes. */
const VARIANTS: Record<string, string> = {
  primary: 'default',
  default: 'default',
  outline: 'outline',
  secondary: 'secondary',
  ghost: 'ghost',
  destructive: 'destructive',
  danger: 'destructive',
  error: 'destructive',
  red: 'destructive',
  gray: 'secondary',
  contrast: 'secondary',
}

const GREEN = 'border-green-500/30 bg-green-500/10 text-green-700 hover:bg-green-500/20 dark:text-emerald-400'
const AMBER = 'border-amber-500/30 bg-amber-500/10 text-amber-700 hover:bg-amber-500/20 dark:text-amber-400'
const BLUE = 'border-blue-500/30 bg-blue-500/10 text-blue-700 hover:bg-blue-500/20 dark:text-blue-400'

const COLOR_CLASSES: Record<string, string> = {
  success: GREEN,
  green: GREEN,
  warning: AMBER,
  warn: AMBER,
  yellow: AMBER,
  orange: AMBER,
  info: BLUE,
  blue: BLUE,
  purple: 'border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-300',
  pink: 'border-pink-500/30 bg-pink-500/10 text-pink-700 dark:text-pink-300',
  teal: 'border-teal-500/30 bg-teal-500/10 text-teal-700 dark:text-teal-300',
}

export type ActionButtonVariant = 'default' | 'outline' | 'secondary' | 'ghost' | 'destructive'

export function actionButtonStyle(
  variant: string | undefined,
  fallback: ActionButtonVariant = 'outline',
): { variant: ActionButtonVariant; className: string } {
  const tone = String(variant ?? '').trim().toLowerCase()
  if (COLOR_CLASSES[tone]) return { variant: 'outline', className: COLOR_CLASSES[tone] }
  return { variant: (VARIANTS[tone] as ActionButtonVariant | undefined) ?? fallback, className: '' }
}
