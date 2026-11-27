import { describe, it, expect, afterEach, vi, beforeEach } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent, h, reactive } from 'vue'
import i18n from '@/plugins/i18n'
import { TooltipProvider } from '@/components/ui/tooltip'
import type { DocType, GruntDocument } from '@/types'

const api = vi.hoisted(() => ({
  getTimeline: vi.fn(),
  getReactionChoices: vi.fn(async () => []),
  deleteComment: vi.fn(async () => undefined),
}))
vi.mock('@/core/api/docs', async (orig) => ({
  ...(await orig<typeof import('@/core/api/docs')>()),
  docsApi: api,
}))
vi.mock('@/core/composables/useDialog', () => ({ useDialog: () => ({}) }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { email: 'me@x' }, hasPerm: () => false }) }))

import SidebarTimeline from '../SidebarTimeline.vue'

const doctype = { name: 'Case', fields: [] } as unknown as DocType

let w: VueWrapper | undefined
afterEach(() => { w?.unmount(); vi.useRealTimers() })
beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers()
  api.getTimeline.mockResolvedValue([])
})

function mountTimeline() {
  const state = reactive({
    document: { name: 'C-1', modified_at: '2026-11-26T10:00:00Z' } as unknown as GruntDocument,
    refreshKey: 0,
  })
  const Timeline = defineComponent({
    setup: () => () => h(TooltipProvider, () =>
      h(SidebarTimeline, { doctype, document: state.document, refreshKey: state.refreshKey })),
  })
  w = mount(Timeline, { global: { plugins: [i18n] } })
  return state
}

async function settle() {
  await flushPromises()
  vi.advanceTimersByTime(300)
  await flushPromises()
}

describe('SidebarTimeline - refresh', () => {
  it('reloads when the document is saved or reloaded (modified_at changes)', async () => {
    const state = mountTimeline()
    await settle()
    expect(api.getTimeline).toHaveBeenCalledTimes(1)

    state.document = { ...state.document, modified_at: '2026-11-26T10:05:00Z' } as GruntDocument
    await settle()
    expect(api.getTimeline).toHaveBeenCalledTimes(2)
  })

  it('reloads once for a burst of room events', async () => {
    const state = mountTimeline()
    await settle()
    state.refreshKey++
    await flushPromises()
    state.refreshKey++
    await flushPromises()
    state.document = { ...state.document, modified_at: '2026-11-26T10:06:00Z' } as GruntDocument
    await settle()
    expect(api.getTimeline).toHaveBeenCalledTimes(2)
  })

  it('keeps the comment box on a refresh of an empty timeline', async () => {
    const state = mountTimeline()
    await settle()
    let resolve!: (v: unknown[]) => void
    api.getTimeline.mockReturnValueOnce(new Promise((r) => { resolve = r }))
    state.refreshKey++
    await settle()
    expect(w!.find('textarea').exists()).toBe(true)
    resolve([])
    await flushPromises()
  })

  it('drops an older answer that arrives after a newer one', async () => {
    const state = mountTimeline()
    await settle()
    let resolveOld!: (v: unknown[]) => void
    api.getTimeline.mockReturnValueOnce(new Promise((r) => { resolveOld = r }))
    state.refreshKey++
    await settle()
    const fresh = [{ type: 'comment', id: 'c2', content: 'нове', user: 'me@x', created_at: '2026-11-26T10:07:00Z' }]
    api.getTimeline.mockResolvedValueOnce(fresh)
    state.refreshKey++
    await settle()
    resolveOld([{ type: 'comment', id: 'c1', content: 'старе', user: 'me@x', created_at: '2026-11-26T10:06:00Z' }])
    await flushPromises()
    expect(w!.text()).toContain('нове')
    expect(w!.text()).not.toContain('старе')
  })

  it('drops a refresh that started before a comment was deleted', async () => {
    const mine = { type: 'comment', id: 'c1', content: 'видалити', user: 'me@x', created_at: '2026-11-26T10:06:00Z' }
    api.getTimeline.mockResolvedValue([mine])
    const state = mountTimeline()
    await settle()
    expect(w!.text()).toContain('видалити')

    let resolveOld!: (v: unknown[]) => void
    api.getTimeline.mockReturnValueOnce(new Promise((r) => { resolveOld = r }))
    state.refreshKey++
    await settle()
    await w!.find('button[aria-label="Delete comment"]').trigger('click')
    await flushPromises()
    expect(w!.text()).not.toContain('видалити')
    resolveOld([mine])
    await flushPromises()
    expect(w!.text()).not.toContain('видалити')
  })
})
