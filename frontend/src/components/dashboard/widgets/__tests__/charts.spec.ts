import { describe, it, expect, afterEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import type { DashboardWidget } from '@/types'

// jsdom lacks these; unovis picks ResizeObserver at import time, so the stubs
// must exist before the widgets are imported.
vi.hoisted(() => {
  globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as any
  ;(SVGElement.prototype as any).getBBox ??= () => ({ x: 0, y: 0, width: 10, height: 10 })
  ;(SVGElement.prototype as any).getComputedTextLength ??= () => 10
})

const push = vi.fn()
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))

import Chart from '../Chart/Chart.vue'
import Donut from '../Donut/Donut.vue'
import Gauge from '../Gauge/Gauge.vue'
import ReportChart from '@/components/reports/ReportChart.vue'

const global = { plugins: [createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false })] }
const widget = (w: Partial<DashboardWidget>) => ({ id: 'w', title: 'Orders', color: 'primary', ...w }) as DashboardWidget

let w: VueWrapper | undefined
afterEach(() => { w?.unmount(); document.body.innerHTML = '' })

describe('dashboard charts on shadcn Chart (unovis)', () => {
  it.each(['chart_line', 'chart_area', 'chart_bar'])('%s renders an SVG chart', async (widget_type) => {
    w = mount(Chart, {
      props: {
        widget: widget({ widget_type }),
        data: { labels: ['2026-10-01', '2026-10-02', '2026-10-03'], groups: { Open: [1, 2, 3], Closed: [0, 1, 1] } },
      },
      attachTo: document.body, global,
    })
    await flushPromises()
    expect(w.find('[data-slot="chart"]').exists()).toBe(true)
    expect(w.find('svg').exists()).toBe(true)
  })

  it('donut renders segments and the legend', async () => {
    w = mount(Donut, {
      props: { widget: widget({ widget_type: 'donut' }), data: { labels: ['A', 'B'], values: [3, 1] } },
      attachTo: document.body, global,
    })
    await flushPromises()
    expect(w.find('svg').exists()).toBe(true)
    expect(w.text()).toContain('75%')
  })

  it('gauge renders the value', async () => {
    w = mount(Gauge, {
      props: { widget: widget({ widget_type: 'gauge', min_value: 0, max_value: 10 }), data: { value: 4 } },
      attachTo: document.body, global,
    })
    await flushPromises()
    expect(w.find('svg').exists()).toBe(true)
    expect(w.text()).toContain('4')
  })

  it.each(['bar', 'pie'] as const)('report chart (%s) renders', async (type) => {
    w = mount(ReportChart, {
      props: {
        config: { type, label_field: 'status', value_fields: ['count', 'amount'], stacked: true },
        columns: [{ fieldname: 'status', label: 'Status' }, { fieldname: 'count', label: 'Count' }, { fieldname: 'amount', label: 'Amount' }],
        data: [{ status: 'Open', count: 3, amount: 10 }, { status: 'Closed', count: 1, amount: 4 }],
      } as any,
      attachTo: document.body, global,
    })
    await flushPromises()
    expect(w.find('svg').exists()).toBe(true)
    expect(w.text()).toContain(type === 'pie' ? 'Open' : 'Count') // legend
  })
})
