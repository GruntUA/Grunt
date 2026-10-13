import { describe, it, expect, afterEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { defineComponent, h, reactive } from 'vue'
import type { WorkspaceLink } from '@/core/api/workspace'

const route = vi.hoisted(() => ({ params: {} as Record<string, unknown>, fullPath: '/app/grunt' }))
const media = vi.hoisted(() => ({ mobile: false }))
vi.mock('vue-router', () => ({ useRoute: () => route, useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/stores/app', () => ({ useAppStore: () => reactive({ counts: {}, active: { color: '' } }) }))
vi.mock('@vueuse/core', async (orig) => {
  const { ref } = await import('vue')
  return { ...(await orig<typeof import('@vueuse/core')>()), useMediaQuery: () => ref(media.mobile) }
})

import { SidebarProvider } from '@/components/ui/sidebar'
import SidebarModule from '../SidebarModule.vue'

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as any

const items = [
  { type: 'DocType', link_to: 'User', label: 'Users', icon: 'user', section: 'Security', sequence: 1 },
  { type: 'DocType', link_to: 'Role', label: 'Roles', icon: 'key', section: 'Security', sequence: 2 },
] as WorkspaceLink[]

let w: VueWrapper | undefined
afterEach(() => { w?.unmount(); document.body.innerHTML = ''; route.params = {}; media.mobile = false })

function mountModule() {
  const Host = defineComponent(() => () => h(SidebarProvider, null, () =>
    h('ul', h(SidebarModule, { section: 'Security', icon: 'shield-check', items, workspaceName: 'grunt', onDrill: () => w!.vm.$emit('drill') }))))
  w = mount(Host, { attachTo: document.body })
  return w
}

describe('SidebarModule', () => {
  it('opens the section items in a panel beside the sidebar', async () => {
    mountModule()
    expect(document.body.textContent).not.toContain('Roles')
    await w!.find('[data-sidebar="menu-button"]').trigger('click')
    await flushPromises()
    const panel = document.body.querySelector('[data-slot="popover-content"]')!
    expect(panel.textContent).toContain('Users')
    expect(panel.textContent).toContain('Roles')
  })

  it('is highlighted while one of its pages is open', async () => {
    route.params = { doctype: 'Role' }
    mountModule()
    expect(w!.find('[data-sidebar="menu-button"]').attributes('data-active')).toBe('true')
  })

  it('drills in on mobile instead of opening a panel', async () => {
    media.mobile = true
    mountModule()
    await w!.find('[data-sidebar="menu-button"]').trigger('click')
    expect(w!.emitted('drill')).toHaveLength(1)
    expect(document.body.querySelector('[data-slot="popover-content"]')).toBeNull()
  })
})
