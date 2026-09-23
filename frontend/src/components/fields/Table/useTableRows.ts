/**
 * Row state for the Table field: the list itself, every mutation (each one is
 * emitted to the form as a fresh array), selection, and undo of the last delete.
 *
 * Every row carries a client-only `__uid` so identity survives reorder / insert /
 * delete — :key, selection and "which row was edited" stay put. The backend
 * ignores the extra key and regenerates child `name`/`idx` itself.
 */
import { computed, ref, watch, type Ref } from 'vue'

export type Row = Record<string, unknown> & { __uid: string }

function genUid(): string {
  return typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `r${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

/** A copy that becomes a new row: no identity of the source carried over. */
function cloneRow(row: Row): Row {
  const { name: _n, id: _i, __uid: _u, ...rest } = row
  return { ...rest, __uid: genUid() }
}

export function useTableRows(opts: {
  modelValue: () => unknown
  onChange: (rows: Row[]) => void
  blankRow: () => Record<string, unknown>
}) {
  const rows = ref<Row[]>([]) as Ref<Row[]>

  // Adopt the incoming value, keeping each known row's uid (matched by child
  // `name`, else by position) so a re-emit from the form doesn't reset keys.
  function adopt(incoming: unknown) {
    const list = Array.isArray(incoming) ? (incoming as Record<string, unknown>[]) : []
    const prev = rows.value
    if (list.length === prev.length && list.every((r, i) => r === prev[i])) return // own echo
    const byName = new Map(prev.filter((r) => r.name != null).map((r) => [String(r.name), r]))
    rows.value = list.map((r, i) => {
      if (typeof r.__uid === 'string') return r as Row
      const carrier = (r.name != null && byName.get(String(r.name))) || prev[i]
      return { ...r, __uid: carrier?.__uid ?? genUid() }
    })
  }
  watch(opts.modelValue, adopt, { immediate: true })

  function commit(next: Row[]) {
    rows.value = next
    opts.onChange(next)
  }

  function indexOf(uid: string): number {
    return rows.value.findIndex((r) => r.__uid === uid)
  }

  function newRow(): Row {
    return { ...opts.blankRow(), __uid: genUid() }
  }

  // ── Single-row mutations ────────────────────────────────────────────────
  function add(): Row {
    const row = newRow()
    commit([...rows.value, row])
    return row
  }

  function insert(uid: string, where: 'above' | 'below'): void {
    const i = indexOf(uid)
    if (i === -1) return
    const next = [...rows.value]
    next.splice(where === 'above' ? i : i + 1, 0, newRow())
    commit(next)
  }

  function duplicate(uid: string): void {
    const i = indexOf(uid)
    if (i === -1) return
    const next = [...rows.value]
    next.splice(i + 1, 0, cloneRow(rows.value[i]))
    commit(next)
  }

  function setCell(uid: string, fieldname: string, value: unknown): void {
    commit(rows.value.map((r) => (r.__uid === uid ? { ...r, [fieldname]: value } : r)))
  }

  function replace(uid: string, data: Record<string, unknown>): void {
    commit(rows.value.map((r) => (r.__uid === uid ? { ...data, __uid: uid } : r)))
  }

  /** New order from drag-and-drop; `idx` follows the visual position. */
  function reorder(ordered: Row[]): void {
    commit(ordered.map((r, i) => ({ ...r, idx: i })))
  }

  // ── Selection ───────────────────────────────────────────────────────────
  const selected = ref<Set<string>>(new Set())

  watch(rows, (list) => {
    const alive = new Set(list.map((r) => r.__uid))
    if ([...selected.value].some((uid) => !alive.has(uid))) {
      selected.value = new Set([...selected.value].filter((uid) => alive.has(uid)))
    }
  })

  const allSelected = computed(
    () => rows.value.length > 0 && rows.value.every((r) => selected.value.has(r.__uid)),
  )
  const headerCheck = computed<boolean | 'indeterminate'>(() =>
    allSelected.value ? true : selected.value.size ? 'indeterminate' : false,
  )

  function toggle(uid: string): void {
    const next = new Set(selected.value)
    if (!next.delete(uid)) next.add(uid)
    selected.value = next
  }

  function toggleAll(): void {
    selected.value = allSelected.value ? new Set() : new Set(rows.value.map((r) => r.__uid))
  }

  function clearSelection(): void {
    selected.value = new Set()
  }

  /** Child `name` of each selected row (uid for rows not saved yet). */
  const selectedNames = computed(() =>
    rows.value.filter((r) => selected.value.has(r.__uid)).map((r) => String(r.name ?? r.__uid)),
  )

  // ── Bulk mutations on the selection ─────────────────────────────────────
  function duplicateSelected(): void {
    const copies = rows.value.filter((r) => selected.value.has(r.__uid)).map(cloneRow)
    commit([...rows.value, ...copies])
    clearSelection()
  }

  function setSelected(fieldname: string, value: unknown): void {
    commit(rows.value.map((r) => (selected.value.has(r.__uid) ? { ...r, [fieldname]: value } : r)))
  }

  // ── Delete + undo ───────────────────────────────────────────────────────
  let lastDeleted: { rows: Row[]; at: number } | null = null

  function removeWhere(pick: (r: Row) => boolean): number {
    const at = rows.value.findIndex(pick)
    if (at === -1) return 0
    const removed = rows.value.filter(pick)
    lastDeleted = { rows: removed, at }
    commit(rows.value.filter((r) => !pick(r)))
    return removed.length
  }

  function remove(uid: string): number {
    return removeWhere((r) => r.__uid === uid)
  }

  function removeSelected(): number {
    const uids = new Set(selected.value)
    clearSelection()
    return removeWhere((r) => uids.has(r.__uid))
  }

  function undoRemove(): void {
    if (!lastDeleted) return
    const next = [...rows.value]
    next.splice(Math.min(lastDeleted.at, next.length), 0, ...lastDeleted.rows)
    lastDeleted = null
    commit(next)
  }

  return {
    rows,
    indexOf,
    add,
    insert,
    duplicate,
    setCell,
    replace,
    reorder,
    remove,
    undoRemove,
    selected,
    headerCheck,
    toggle,
    toggleAll,
    clearSelection,
    selectedNames,
    duplicateSelected,
    setSelected,
    removeSelected,
  }
}
