import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import type { QueryClient } from '@tanstack/vue-query'
import { useFormDocWatcher } from '../useFormDocWatcher'

function setup(opts: { dirty?: boolean } = {}) {
  const handlers: Record<string, (data: unknown) => void> = {}
  const invalidateQueries = vi.fn()
  const toast = { info: vi.fn() }
  const document = ref<Record<string, unknown> | null>({ name: 'C-1', modified_at: '2026-11-26T10:00:00.123+00:00' })
  const { timelineRefreshKey } = useFormDocWatcher({
    onEvent: (event, handler) => { handlers[event] = handler },
    isDirty: ref(!!opts.dirty),
    doctype: 'Case',
    id: 'C-1',
    queryClient: { invalidateQueries } as unknown as QueryClient,
    toast,
    document,
    userEmail: () => 'me@x',
  })
  const emit = (event: string, data: unknown) => handlers[event](data)
  return { emit, invalidateQueries, toast, timelineRefreshKey }
}

describe('useFormDocWatcher', () => {
  it("reloads another user's save, with a toast", () => {
    const s = setup()
    s.emit('doc_change', { source: 'save', modified_at: '2026-11-26T10:01:00+00:00', modified_by: 'boss@x' })
    expect(s.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['document', 'Case', 'C-1'] })
    expect(s.toast.info).toHaveBeenCalledOnce()
    expect(s.timelineRefreshKey.value).toBe(1)
  })

  it('skips the save the form already shows (its own)', () => {
    const s = setup()
    s.emit('doc_change', { source: 'save', modified_at: '2026-11-26T10:00:00.123456Z', modified_by: 'me@x' })
    expect(s.invalidateQueries).not.toHaveBeenCalled()
    expect(s.timelineRefreshKey.value).toBe(1)
  })

  it('reloads its own save from another tab without a toast', () => {
    const s = setup()
    s.emit('doc_change', { source: 'save', modified_at: '2026-11-26T10:02:00Z', modified_by: 'me@x' })
    expect(s.invalidateQueries).toHaveBeenCalledOnce()
    expect(s.toast.info).not.toHaveBeenCalled()
  })

  it('keeps unsaved edits', () => {
    const s = setup({ dirty: true })
    s.emit('doc_change', { source: 'save', modified_at: '2026-11-26T10:01:00Z', modified_by: 'boss@x' })
    expect(s.invalidateQueries).not.toHaveBeenCalled()
    expect(s.timelineRefreshKey.value).toBe(1)
  })

  it('a timeline change only refreshes the timeline', () => {
    const s = setup()
    s.emit('timeline_change', { source: 'Comment' })
    expect(s.invalidateQueries).not.toHaveBeenCalled()
    expect(s.timelineRefreshKey.value).toBe(1)
  })
})
