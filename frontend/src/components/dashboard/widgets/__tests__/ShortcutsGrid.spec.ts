import { describe, it, expect, afterEach, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'

const push = vi.fn()
vi.mock('vue-router', () => ({ useRouter: () => ({ push }), useRoute: () => ({ params: {} }) }))

import ShortcutsGrid from '../ShortcutsGrid/ShortcutsGrid.vue'
import { i18n } from '@/plugins/i18n'
import type { DashboardWidget, ShortcutItem } from '@/types'

let w: VueWrapper | undefined
afterEach(() => { w?.unmount(); push.mockReset() })

function mountTiles(tiles: ShortcutItem[]) {
  const widget = { id: 'w1', widget_type: 'shortcuts_grid', content: JSON.stringify(tiles) } as DashboardWidget
  w = mount(ShortcutsGrid, { props: { widget, workspaceName: 'hrm' }, global: { plugins: [i18n] } })
  return w
}

describe('ShortcutsGrid', () => {
  it('opens a DocType list with the tile filters and view', async () => {
    const wrap = mountTiles([{
      title: 'Відпустки',
      link_type: 'DocType',
      link_to: 'Absence',
      filters: { absence_type: 'Відпустка', to_date__gte: '2026-01-01' },
      view: 'calendar',
    }])
    await wrap.find('button').trigger('click')
    const url = new URL(push.mock.calls[0][0], 'http://x')
    expect(url.pathname).toBe('/app/hrm/Absence')
    expect(url.searchParams.get('filter[absence_type__eq]')).toBe('Відпустка')
    expect(url.searchParams.get('filter[to_date__gte]')).toBe('2026-01-01')
    expect(url.searchParams.get('view')).toBe('calendar')
  })

  it('a plain tile opens the bare list', async () => {
    const wrap = mountTiles([{ title: 'Співробітники', link_type: 'DocType', link_to: 'Employee' }])
    await wrap.find('button').trigger('click')
    expect(push).toHaveBeenCalledWith('/app/hrm/Employee')
  })
})
