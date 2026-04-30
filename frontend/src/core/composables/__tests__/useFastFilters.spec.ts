import { describe, it, expect, vi, afterEach } from 'vitest'
import { computed, nextTick, ref } from 'vue'
import { useFastFilters } from '../useFastFilters'
import type { FastFilter } from '@/types'

function makeFastFilter(overrides: Partial<FastFilter> = {}): FastFilter {
  return {
    id: 'as_of_date',
    field: 'valid_from',
    operator: 'lte_or_null',
    label: 'Станом на дату',
    input_type: 'date',
    default_value: null,
    on_change: { mode: 'local', debounce_ms: 0 },
    enabled_in: ['list', 'tree'],
    ...overrides,
  }
}

afterEach(() => {
  vi.useRealTimers()
})

describe('useFastFilters', () => {
  it('resolves date default token "today" to local ISO date', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-04-30T12:00:00Z'))

    const defs = computed(() => [makeFastFilter({ default_value: 'today' })])
    const fastFilterValues = ref<Record<string, string>>({})

    const { rawFastFilters } = useFastFilters(defs, 'list', fastFilterValues)
    await nextTick()

    expect(fastFilterValues.value.as_of_date).toBe('2026-04-30')
    expect(rawFastFilters.value).toEqual({ valid_from__lte_or_null: '2026-04-30' })
  })

  it('uses user-selected date instead of default token', async () => {
    const defs = computed(() => [makeFastFilter({ default_value: 'today' })])
    const fastFilterValues = ref<Record<string, string>>({ as_of_date: '2025-01-15' })

    const { rawFastFilters } = useFastFilters(defs, 'tree', fastFilterValues)
    await nextTick()

    expect(rawFastFilters.value).toEqual({ valid_from__lte_or_null: '2025-01-15' })
  })

  it('reapplies today default when as_of_date is cleared', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-04-30T12:00:00Z'))

    const defs = computed(() => [makeFastFilter({ default_value: 'today' })])
    const fastFilterValues = ref<Record<string, string>>({ as_of_date: '' })

    const { rawFastFilters } = useFastFilters(defs, 'list', fastFilterValues)
    await nextTick()

    expect(fastFilterValues.value.as_of_date).toBe('2026-04-30')
    expect(rawFastFilters.value).toEqual({ valid_from__lte_or_null: '2026-04-30' })
  })
})
