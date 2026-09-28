import { afterEach, describe, expect, it, vi } from 'vitest'
import { useTaskTracker } from '@/core/composables/useTaskTracker'

const GB = 1024 ** 3

describe('useTaskTracker ETA', () => {
  afterEach(() => {
    useTaskTracker().dismiss('backup')
    vi.useRealTimers()
  })

  it('follows the recent pace, not the average since the start', () => {
    vi.useFakeTimers()
    const tracker = useTaskTracker()
    const at = (seconds: number, count: number) => {
      vi.setSystemTime(seconds * 1000)
      tracker.update({ task_id: 'backup', title: 'Backup', count, total: 3 * GB })
    }
    // A fast first part: 1 GB in 5 s…
    at(0, 0)
    at(5, GB)
    // …then files at 10 MB/s for a minute.
    for (let s = 10; s <= 65; s += 5) at(s, GB + (s - 5) * 10 * 1024 ** 2)

    const task = tracker.tasks.value.find(t => t.id === 'backup')!
    const left = (3 * GB - task.count) / (10 * 1024 ** 2)
    expect(task.etaSeconds).toBeCloseTo(left, 0) // ~2.8 min, the average would say ~1.4
  })

  it('is unknown until a few seconds are measured', () => {
    vi.useFakeTimers()
    const tracker = useTaskTracker()
    vi.setSystemTime(0)
    tracker.update({ task_id: 'backup', title: 'Backup', count: 0, total: GB })
    vi.setSystemTime(1000)
    tracker.update({ task_id: 'backup', title: 'Backup', count: 100, total: GB })
    expect(tracker.tasks.value[0]!.etaSeconds).toBeUndefined()
  })

  it('keeps step N of M', () => {
    const tracker = useTaskTracker()
    tracker.update({ task_id: 'backup', title: 'Backup', count: 1, total: 10, step: 2, steps: 3 })
    tracker.update({ task_id: 'backup', title: 'Backup', count: 2, total: 10 })
    expect(tracker.tasks.value[0]).toMatchObject({ step: 2, steps: 3 })
  })
})
