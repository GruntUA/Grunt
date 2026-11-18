import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

const get = vi.fn()
const save = vi.fn()
vi.mock('@/core/api/viewSettings', () => ({
  viewSettingsApi: { get: (...a: unknown[]) => get(...a), save: (...a: unknown[]) => save(...a) },
}))

import { clearViewSettingsCache, useViewSetting } from '../useViewSetting'

const flush = () => new Promise((r) => setTimeout(r, 0))

describe('useViewSetting', () => {
  beforeEach(() => {
    localStorage.clear()
    clearViewSettingsCache()
    save.mockResolvedValue(undefined)
  })
  afterEach(() => { vi.useRealTimers(); get.mockReset(); save.mockReset() })

  it('starts from the cache, then takes the server value', async () => {
    localStorage.setItem('k', JSON.stringify(['a']))
    get.mockResolvedValue({ columns: ['b', 'c'] })
    const v = useViewSetting<string[]>('Task', 'columns', 'k')
    expect(v.value).toEqual(['a'])
    await flush()
    expect(v.value).toEqual(['b', 'c'])
    expect(JSON.parse(localStorage.getItem('k')!)).toEqual(['b', 'c'])
    expect(save).not.toHaveBeenCalled() // the server's own value isn't sent back
  })

  it('writes the cache at once and the server after a pause; null resets', async () => {
    get.mockResolvedValue({})
    vi.useFakeTimers()
    const v = useViewSetting<string[]>('Task', 'columns', 'k')
    v.value = ['x']
    expect(JSON.parse(localStorage.getItem('k')!)).toEqual(['x'])
    v.value = ['x', 'y']
    await vi.advanceTimersByTimeAsync(1000)
    expect(save).toHaveBeenCalledTimes(1) // debounced
    expect(save).toHaveBeenCalledWith('Task', 'columns', ['x', 'y'])
    v.value = null
    expect(localStorage.getItem('k')).toBeNull()
    await vi.advanceTimersByTimeAsync(1000)
    expect(save).toHaveBeenLastCalledWith('Task', 'columns', null)
  })

  it('sends a cached value up once when the server has none', async () => {
    localStorage.setItem('k', JSON.stringify(['old']))
    get.mockResolvedValue({})
    useViewSetting<string[]>('Task', 'columns', 'k')
    await flush()
    expect(save).toHaveBeenCalledWith('Task', 'columns', ['old'])
  })

  it('drops a cached value of the wrong shape and loads once per DocType', async () => {
    localStorage.setItem('k', JSON.stringify({ not: 'a list' }))
    get.mockResolvedValue({})
    const valid = (v: unknown): v is string[] => Array.isArray(v)
    const a = useViewSetting<string[]>('Task', 'columns', 'k', { valid })
    useViewSetting<string[]>('Task', 'quick_filters', 'k2', { valid })
    expect(a.value).toBeNull()
    await nextTick()
    expect(get).toHaveBeenCalledTimes(1)
  })
})
