import { describe, it, expect, afterEach, vi, beforeEach } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent, h, reactive } from 'vue'
import i18n from '@/plugins/i18n'
import { TooltipProvider } from '@/components/ui/tooltip'
import type { DocType, GruntDocument } from '@/types'

const api = vi.hoisted(() => ({ getTimeline: vi.fn() }))
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
})
