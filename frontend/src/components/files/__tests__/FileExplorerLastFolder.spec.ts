import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import i18n from '@/plugins/i18n'

const folders: Record<string, { name: string; folder_name: string }> = {
  home: { name: 'home', folder_name: 'Home' },
  work: { name: 'work', folder_name: 'Work' },
}

vi.mock('@/core/api/files', () => ({
  filesApi: {
    list: async () => ({ items: [], total: 0 }),
    homeFolder: async () => ({ name: 'home' }),
    storageUsage: async () => null,
  },
}))
vi.mock('@/core/api/docs', () => ({
  docsApi: {
    get: async (_dt: string, name: string) => {
      if (!folders[name]) throw new Error('Not found')
      return folders[name]
    },
    getTreeAncestors: async () => [],
    getTreeChildren: async () => [],
  },
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { email: 'me@x' } }) }))

import FileExplorer from '../FileExplorer.vue'
import { lastFolder, rememberFolder } from '@/core/composables/useFolderPicker'

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as any

let w: VueWrapper<any> | undefined
beforeEach(() => localStorage.clear())
afterEach(() => { w?.unmount() })

async function mountExplorer(props: Record<string, unknown> = {}) {
  w = mount(FileExplorer, { props: { mode: 'file', ...props }, global: { plugins: [i18n] } })
  await flushPromises()
  return w.vm.current as string
}

describe('FileExplorer last folder', () => {
  it('opens the folder the user was in last', async () => {
    rememberFolder('me@x', 'work')
    expect(await mountExplorer()).toBe('work')
  })

  it('falls back to home when that folder is gone, and remembers home', async () => {
    rememberFolder('me@x', 'gone')
    expect(await mountExplorer()).toBe('home')
    expect(lastFolder('me@x')).toBe('home')
  })

  it('an explicit folder wins, and becomes the last one', async () => {
    rememberFolder('me@x', 'home')
    expect(await mountExplorer({ folder: 'work' })).toBe('work')
    expect(lastFolder('me@x')).toBe('work')
  })

  it('keeps one memory per user', async () => {
    rememberFolder('other@x', 'work')
    expect(await mountExplorer()).toBe('home')
  })
})
