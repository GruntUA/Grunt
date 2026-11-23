import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import type { NotificationPreferences as Prefs } from '@/core/api/notifications'

const state = vi.hoisted(() => ({ data: null as unknown }))

vi.mock('@/core/api/notifications', () => ({
  notificationsApi: {
    preferences: vi.fn(async () => state.data),
    setPreference: vi.fn(async (channel: string, enabled: boolean, notification?: string | null) => {
      const prefs = state.data as Prefs
      const off = prefs.off.filter((r) => !(r.notification === (notification ?? null) && r.channel === channel))
      if (!enabled) off.push({ notification: notification ?? null, channel })
      state.data = { ...prefs, off }
      return state.data
    }),
  },
}))

import i18n from '@/plugins/i18n'
import { notificationsApi } from '@/core/api/notifications'
import NotificationPreferences from '../NotificationPreferences.vue'

function prefs(off: Prefs['off'] = []): Prefs {
  return {
    channels: [{ value: 'in_app', label: 'Bell' }, { value: 'email', label: 'Email' }],
    rules: [
      { name: 'Task assigned', label: 'Task assigned', ref_doctype: null, channels: ['in_app', 'email'], mandatory: false },
      { name: 'Approval', label: 'Approval', ref_doctype: null, channels: ['email'], mandatory: true },
    ],
    off,
  }
}

let w: VueWrapper | undefined
afterEach(() => { w?.unmount(); vi.clearAllMocks() })

async function mountIt(off: Prefs['off'] = []) {
  state.data = prefs(off)
  w = mount(NotificationPreferences, { global: { plugins: [i18n] }, attachTo: document.body })
  await flushPromises()
  return w
}

const switches = (w: VueWrapper) => w.findAll('[role="switch"]')
const checked = (w: VueWrapper) => switches(w).map((s) => s.attributes('data-state') === 'checked')
const disabled = (w: VueWrapper) => switches(w).map((s) => s.attributes('disabled') !== undefined)

describe('NotificationPreferences dialog', () => {
  it('shows all rows on, a dash for a channel a rule does not use, a locked mandatory rule', async () => {
    const w = await mountIt()
    // All (bell, email) · Task assigned (bell, email) · Approval (email)
    expect(checked(w)).toEqual([true, true, true, true, true])
    expect(disabled(w)).toEqual([false, false, false, false, true])
    expect(w.text()).toContain('—')
  })

  it('turning a rule off in a channel saves it', async () => {
    const w = await mountIt()
    await switches(w)[3]!.trigger('click')
    await flushPromises()
    expect(notificationsApi.setPreference).toHaveBeenCalledWith('email', false, 'Task assigned')
    expect(checked(w)).toEqual([true, true, true, false, true])
  })

  it('a channel turned off for all notifications locks its rule switches, but not mandatory ones', async () => {
    const w = await mountIt([{ notification: null, channel: 'email' }])
    expect(checked(w)).toEqual([true, false, true, false, true])
    expect(disabled(w)).toEqual([false, false, false, true, true])
  })
})
