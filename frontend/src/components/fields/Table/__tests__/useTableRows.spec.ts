import { describe, expect, it } from 'vitest'
import { nextTick, ref } from 'vue'
import { useTableRows, type Row } from '../useTableRows'

function setup(initial: Record<string, unknown>[] = []) {
  const model = ref<unknown>(initial)
  const emitted: Row[][] = []
  const table = useTableRows({
    modelValue: () => model.value,
    onChange: (rows) => {
      emitted.push(rows)
      model.value = rows // the form echoes the value back
    },
    blankRow: () => ({ qty: null, ok: false }),
  })
  return { table, model, emitted }
}

const names = (rows: Row[]) => rows.map((r) => r.name ?? r.qty)

describe('useTableRows', () => {
  it('gives every row a uid and keeps it when the form re-sends the rows', async () => {
    const { table, model } = setup([{ name: 'a' }, { name: 'b' }])
    const uids = table.rows.value.map((r) => r.__uid)
    expect(new Set(uids).size).toBe(2)

    model.value = [{ name: 'b' }, { name: 'a' }] // reloaded, reordered, no uids
    await nextTick()
    expect(table.rows.value.map((r) => r.__uid)).toEqual([uids[1], uids[0]])
  })

  it('adds, inserts and duplicates without copying identity', () => {
    const { table } = setup([{ name: 'a', qty: 1 }])
    const a = table.rows.value[0].__uid
    table.insert(a, 'above')
    table.duplicate(a)
    table.add()
    const rows = table.rows.value
    expect(rows.map((r) => r.qty)).toEqual([null, 1, 1, null])
    expect(rows[2].name).toBeUndefined()
    expect(new Set(rows.map((r) => r.__uid)).size).toBe(4)
  })

  it('deletes with undo back into the same place', () => {
    const { table } = setup([{ name: 'a' }, { name: 'b' }, { name: 'c' }])
    const b = table.rows.value[1].__uid
    expect(table.remove(b)).toBe(1)
    expect(names(table.rows.value)).toEqual(['a', 'c'])
    table.undoRemove()
    expect(names(table.rows.value)).toEqual(['a', 'b', 'c'])
  })

  it('runs bulk actions on the selection and reports child names', () => {
    const { table } = setup([{ name: 'a' }, { name: 'b' }, { qty: 7 }])
    const [a, , fresh] = table.rows.value
    table.toggle(a.__uid)
    table.toggle(fresh.__uid)
    expect(table.headerCheck.value).toBe('indeterminate')
    expect(table.selectedNames.value).toEqual(['a', fresh.__uid])

    table.setSelected('qty', 5)
    expect(table.rows.value.map((r) => r.qty)).toEqual([5, undefined, 5])

    expect(table.removeSelected()).toBe(2)
    expect(names(table.rows.value)).toEqual(['b'])
    expect(table.selected.value.size).toBe(0)
    table.undoRemove()
    expect(table.rows.value).toHaveLength(3)
  })

  it('select-all toggles every row', () => {
    const { table } = setup([{ name: 'a' }, { name: 'b' }])
    table.toggleAll()
    expect(table.headerCheck.value).toBe(true)
    table.toggleAll()
    expect(table.headerCheck.value).toBe(false)
  })

  it('reorder rewrites idx to the visual position', () => {
    const { table, emitted } = setup([{ name: 'a' }, { name: 'b' }])
    table.reorder([...table.rows.value].reverse())
    expect(emitted.at(-1)!.map((r) => [r.name, r.idx])).toEqual([
      ['b', 0],
      ['a', 1],
    ])
  })
})
