import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }), useRoute: () => ({ params: {} }) }))

const list = vi.fn()
vi.mock('@/core/api/docs', () => ({ docsApi: { list: (...a: unknown[]) => list(...a), update: vi.fn() } }))

import CalendarView from '../CalendarView.vue'
import { i18n } from '@/plugins/i18n'
import type { DocType } from '@/types'

let w: VueWrapper | undefined
afterEach(() => { w?.unmount(); list.mockReset(); vi.useRealTimers() })
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date(2026, 10, 18)) // листопад 2026: сітка 2026-10-26 … 2026-12-06
})

function dt(extra: Partial<DocType> = {}): DocType {
  return { name: 'Absence', fields: [], title_field: 'employee', ...extra } as DocType
}

async function mountView(doctype: DocType, props: Record<string, unknown> = {}) {
  list.mockResolvedValue({ data: [] })
  w = mount(CalendarView, {
    props: { doctype, dateField: 'from_date', ...props },
    global: { plugins: [i18n] },
  })
  await flushPromises()
  return w
}

describe('CalendarView fetch window', () => {
  it('asks only for documents that overlap the visible grid', async () => {
    await mountView(dt())
    expect(list).toHaveBeenCalledTimes(1)
    const [, params] = list.mock.calls[0]
    expect(params.rawFilters).toEqual({ from_date__lte: '2026-12-06', from_date__gte: '2026-10-26' })
  })

  it('with an end field: spans ending in the grid, plus one-day documents without an end', async () => {
    await mountView(dt({ calendar_end_date_field: 'to_date', calendar_title_field: 'employee_name' }))
    expect(list).toHaveBeenCalledTimes(2)
    const windows = list.mock.calls.map(([, p]) => p.rawFilters)
    expect(windows).toContainEqual({ from_date__lte: '2026-12-06', to_date__gte: '2026-10-26' })
    expect(windows).toContainEqual({
      from_date__lte: '2026-12-06',
      to_date__isnull: '1',
      from_date__gte: '2026-10-26',
    })
    expect(list.mock.calls[0][1].fields.split(',')).toContain('employee_name')
  })

  it('passes the list filters and reloads when they change', async () => {
    const filters = [{ fieldname: 'absence_type', op: '=', value: 'Відпустка' }]
    const view = await mountView(dt(), { activeFilters: filters })
    expect(list.mock.calls[0][1].filters).toEqual(filters)
    await view.setProps({ activeFilters: [] })
    await flushPromises()
    expect(list).toHaveBeenCalledTimes(2)
    expect(list.mock.calls[1][1].filters).toEqual([])
  })
})

describe('CalendarView week start', () => {
  afterEach(() => { i18n.global.locale.value = 'uk' })

  it('starts the week on the language\'s first day', async () => {
    // uk - Monday (the grid above: 2026-10-26 …); en - Sunday: 2026-11-01 … 2026-12-05.
    i18n.global.locale.value = 'en'
    await mountView(dt())
    expect(list.mock.calls[0][1].rawFilters).toEqual({
      from_date__lte: '2026-12-05',
      from_date__gte: '2026-11-01',
    })
  })
})
