import { describe, it, expect } from 'vitest'
import { useDialog } from '@/core/composables/useDialog'

describe('useDialog.select', () => {
  it('opens a form dialog with a Table field and maps the selection out', async () => {
    const d = useDialog()
    const promise = d.select({
      title: 'Оберіть заявки',
      columns: [
        { key: 'name', label: 'Номер' },
        { key: 'status', label: 'Статус', width: '120px' },
      ],
      rows: [{ name: 'MR-1', status: 'Pending' }, { name: 'MR-2', status: 'Pending' }],
      primaryLabel: 'Отримати позиції',
    })

    // renderer state
    expect(d.state.type).toBe('dialog')
    expect(d.state.primaryLabel).toBe('Отримати позиції')
    const table = d.state.fields.at(-1)!
    expect(table.fieldtype).toBe('Table')
    expect(table.multiple).toBe(true)
    expect(table.rowKey).toBe('name')

    // simulate the user confirming with two rows checked
    d.close({ __selection: [{ name: 'MR-1' }, { name: 'MR-2' }] })
    await expect(promise).resolves.toEqual([{ name: 'MR-1' }, { name: 'MR-2' }])
  })

  it('resolves null when cancelled', async () => {
    const d = useDialog()
    const promise = d.select({ title: 't', columns: [], rows: [] })
    d.close(undefined) // cancel
    await expect(promise).resolves.toBeNull()
  })

  it('single-select returns one row (or null), not an array', async () => {
    const d = useDialog()
    const promise = d.select({ title: 't', columns: [{ key: 'name', label: 'N' }], rows: [], multiple: false })
    expect(d.state.fields.at(-1)!.multiple).toBe(false)
    d.close({ __selection: { name: 'A' } })
    await expect(promise).resolves.toEqual({ name: 'A' })
  })

  it('extra filter fields are rendered before the table', async () => {
    const d = useDialog()
    const promise = d.select({
      title: 't',
      columns: [{ key: 'name', label: 'N' }],
      rows: [],
      fields: [{ fieldname: 'status', label: 'Статус', fieldtype: 'Select', options: 'Pending\nDone' }],
    })
    expect(d.state.fields.map(f => f.fieldname)).toEqual(['status', '__selection'])
    d.close(undefined)
    await promise
  })
})
