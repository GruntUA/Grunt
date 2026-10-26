import { describe, it, expect, afterEach, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }), useRoute: () => ({ params: {} }) }))

import FormDashboard from '../FormDashboard.vue'
import { createFormDashboard } from '@/core/scripting/formDashboard'
import { i18n } from '@/plugins/i18n'

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as any

let w: VueWrapper | undefined
afterEach(() => { w?.unmount() })

function mountGraph(type: 'line' | 'bar' | 'area', currency?: string) {
  const dash = createFormDashboard()
  dash.render_graph({
    type,
    currency,
    data: {
      labels: ['2026-01', '2026-02'],
      datasets: [
        { name: 'Іваненко', values: [125000, 130000] },
        { name: 'Петренко', values: [90000, 95000] },
      ],
    },
  })
  w = mount(FormDashboard, { props: { dashboard: dash.state }, global: { plugins: [i18n] } })
  return w
}

describe('FormDashboard graph', () => {
  it('formats money in tooltips and compact numbers on the axis', () => {
    const wrap = mountGraph('line', 'UAH')
    const tips = wrap.findAll('circle title').map((t) => t.text())
    expect(tips[0]).toMatch(/Іваненко \(2026-01\): 125\s000,00\s₴/)
    const axis = wrap.findAll('text').map((t) => t.text()).join(' ')
    expect(axis).toMatch(/130\s?тис/) // max value, compact
  })

  it("draws a bare line for 'line' and a filled area for 'area'", () => {
    const line = mountGraph('line')
    expect(line.findAll('path[fill^="url(#area-grad"]')).toHaveLength(0)
    line.unmount()
    const area = mountGraph('area')
    expect(area.findAll('path[fill^="url(#area-grad"]')).toHaveLength(2)
  })

  it('hides a series when its legend entry is clicked', async () => {
    const wrap = mountGraph('line')
    const legend = wrap.findAll('button[aria-pressed]')
    expect(legend).toHaveLength(2)
    await legend[1].trigger('click')
    expect(legend[1].attributes('aria-pressed')).toBe('false')
    const visibleLines = wrap.findAll('path[stroke]').filter((p) => (p.element as HTMLElement).style.display !== 'none')
    expect(visibleLines).toHaveLength(1)
    await legend[1].trigger('click')
    expect(legend[1].attributes('aria-pressed')).toBe('true')
  })
})
