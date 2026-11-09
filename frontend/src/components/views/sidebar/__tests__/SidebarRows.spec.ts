import { describe, it, expect, afterEach } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent, h, type PropType } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import i18n from '@/plugins/i18n'
import type { SidebarRow } from '@/core/api/docs'
import { TooltipProvider } from '@/components/ui/tooltip'
import SidebarRows from '../SidebarRows.vue'

let w: VueWrapper | undefined
afterEach(() => w?.unmount())

const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)', component: { template: '<div />' } }] })

// The desk mounts it inside the app's TooltipProvider.
const Rows = defineComponent({
  props: { rows: { type: Array as PropType<SidebarRow[]>, required: true } },
  setup: (props) => () => h(TooltipProvider, () => h(SidebarRows, { rows: props.rows })),
})

describe('SidebarRows', () => {
  it('shows a row moment relative, after its badge', () => {
    const due = new Date(Date.now() + 3 * 3600 * 1000).toISOString()
    w = mount(Rows, {
      props: { rows: [{ label: 'Reply in 4h', value: 'On track', indicator: 'primary', datetime: due }] },
      global: { plugins: [i18n, router] },
    })
    const time = w.find('time')
    expect(time.attributes('datetime')).toBe(due)
    expect(time.text()).toMatch(/3/) // «in 3 hours» in the reader's language
    expect(w.text()).toContain('On track')
  })

  it('a row without a moment has no time', () => {
    w = mount(Rows, { props: { rows: [{ label: 'ID', value: 'X-1' }] }, global: { plugins: [i18n, router] } })
    expect(w.find('time').exists()).toBe(false)
  })
})
