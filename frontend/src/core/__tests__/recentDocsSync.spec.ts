import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const get = vi.fn()
const save = vi.fn()
vi.mock('@/core/api/viewSettings', () => ({
  ANY_DOCTYPE: '*',
  viewSettingsApi: { get: (...a: unknown[]) => get(...a), save: (...a: unknown[]) => save(...a) },
}))

import { pushRecent, readRecent, syncRecent } from '../recentDocs'

const doc = (id: string, ts: number, doctype = 'Task') => ({ workspace: 'w', doctype, id, title: id, ts })

describe('recent documents on the server', () => {
  beforeEach(() => { localStorage.clear(); vi.useFakeTimers(); save.mockResolvedValue(undefined) })
  afterEach(() => { vi.useRealTimers(); get.mockReset(); save.mockReset() })

  it('merges the server history with the local one, newest first', async () => {
    localStorage.setItem('grunt_recent_docs', JSON.stringify([doc('a', 30), doc('b', 10)]))
    get.mockResolvedValue({ recent: [doc('c', 20), doc('b', 5)] })
    await syncRecent()
    expect(readRecent(['w']).map((d) => d.id)).toEqual(['a', 'c', 'b'])
    await vi.advanceTimersByTimeAsync(3000)
    expect(save).toHaveBeenCalledTimes(1) // the server lacked "a"
  })

  it('keeps the same id of two DocTypes apart and saves once for several opens', async () => {
    pushRecent({ workspace: 'w', doctype: 'Task', id: '1', title: 't' })
    pushRecent({ workspace: 'w', doctype: 'Note', id: '1', title: 'n' })
    expect(readRecent(['w']).map((d) => d.doctype)).toEqual(['Note', 'Task'])
    await vi.advanceTimersByTimeAsync(3000)
    expect(save).toHaveBeenCalledTimes(1)
    expect(save.mock.calls[0][0]).toBe('*')
  })
})
