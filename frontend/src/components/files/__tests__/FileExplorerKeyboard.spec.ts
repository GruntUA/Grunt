import { describe, it, expect, afterEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import i18n from '@/plugins/i18n'

const file = (id: string, filename: string) => ({ id, filename, content_type: 'text/plain', size_bytes: 10, url: `/f/${id}` })

vi.mock('@/core/api/files', () => ({
  filesApi: {
    list: async () => ({ items: [file('a', 'a.txt'), file('b', 'b.txt'), file('c', 'c.txt')], total: 3 }),
    homeFolder: async () => ({ name: 'home' }),
    storageUsage: async () => null,
  },
}))
vi.mock('@/core/api/docs', () => ({
  docsApi: {
    get: async () => ({ name: 'home', folder_name: 'Home' }),
    getTreeAncestors: async () => [],
    getTreeChildren: async () => [],
  },
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { email: 'me@x' } }) }))

import FileExplorer from '../FileExplorer.vue'

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as any
Element.prototype.scrollIntoView ??= () => {}

let w: VueWrapper | undefined
afterEach(() => { w?.unmount(); document.body.innerHTML = '' })

async function mountExplorer() {
  w = mount(FileExplorer, { props: { mode: 'file', folder: 'home', multiple: true }, attachTo: document.body, global: { plugins: [i18n] } })
  await flushPromises()
  const list = w.find('[role="listbox"]')
  ;(list.element as HTMLElement).focus()
  return list
}

const press = (list: any, key: string, opts: KeyboardEventInit = {}) => list.trigger('keydown', { key, ...opts })
const selectedNames = () => w!.findAll('[role="option"][aria-selected="true"]').map((o) => o.text())

describe('FileExplorer keyboard', () => {
  it('moves the selection with the arrow keys and announces the active entry', async () => {
    const list = await mountExplorer()
    await press(list, 'ArrowDown')
    expect(selectedNames().join()).toContain('a.txt')
    await press(list, 'ArrowDown')
    expect(selectedNames()).toHaveLength(1)
    expect(selectedNames()[0]).toContain('b.txt')
    const activeId = list.attributes('aria-activedescendant')!
    expect(document.getElementById(activeId)?.textContent).toContain('b.txt')
    await press(list, 'End')
    expect(selectedNames()[0]).toContain('c.txt')
  })

  it('extends with Shift, toggles with Space and opens with Enter', async () => {
    const list = await mountExplorer()
    await press(list, 'ArrowDown')
    await press(list, 'ArrowDown', { shiftKey: true })
    expect(selectedNames()).toHaveLength(2)
    await press(list, ' ')
    expect(selectedNames()).toHaveLength(1)
    await press(list, 'Enter')
    expect(w!.emitted('activate')?.at(-1)?.[0]).toMatchObject({ id: 'b' })
  })
})
