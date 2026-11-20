import { describe, it, expect, afterEach, vi, beforeEach } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import i18n from '@/plugins/i18n'
import { TooltipProvider } from '@/components/ui/tooltip'
import type { DocType, GruntDocument } from '@/types'

const api = vi.hoisted(() => ({
  getTimeline: vi.fn(),
  emailComposeContext: vi.fn(),
  sendEmail: vi.fn(),
  renderEmailTemplate: vi.fn(),
}))
vi.mock('@/core/api/docs', async (orig) => ({
  ...(await orig<typeof import('@/core/api/docs')>()),
  docsApi: api,
}))

const form = vi.hoisted(() => vi.fn())
const msgprint = vi.hoisted(() => vi.fn())
vi.mock('@/core/composables/useDialog', () => ({ useDialog: () => ({ form, msgprint }) }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { email: 'me@x' }, hasPerm: () => false }) }))

import SidebarTimeline from '../SidebarTimeline.vue'

const doctype = { name: 'MailCase', fields: [] } as unknown as DocType
const document = { name: 'C-1' } as unknown as GruntDocument

const LETTER = {
  type: 'email',
  id: 'm1',
  direction: 'Incoming',
  status: 'Received',
  subject: 'Не працює ліхтар',
  sender: 'citizen@example.org',
  recipients: 'support@example.com',
  cc: null,
  content: '<p>Біля будинку 5</p>',
  attachments: [{ filename: 'фото.pdf', file: '/files/x.pdf' }],
  user: 'citizen@example.org',
  created_at: '2026-11-20T10:00:00Z',
}

const Timeline = defineComponent({
  setup: () => () => h(TooltipProvider, () => h(SidebarTimeline, { doctype, document })),
})

let w: VueWrapper | undefined
afterEach(() => w?.unmount())
beforeEach(() => {
  vi.clearAllMocks()
  api.getTimeline.mockResolvedValue([LETTER])
})

async function mountTimeline() {
  w = mount(Timeline, { global: { plugins: [i18n] } })
  await flushPromises()
  return w
}

describe('SidebarTimeline - letters', () => {
  it('shows a letter with its subject, text and files', async () => {
    const wrapper = await mountTimeline()
    expect(wrapper.text()).toContain('Не працює ліхтар')
    expect(wrapper.text()).toContain('Біля будинку 5')
    expect(wrapper.find('a[href="/files/x.pdf"]').text()).toBe('фото.pdf')
  })

  it('replies to a letter from the dialog, threaded to it', async () => {
    api.emailComposeContext.mockResolvedValue({
      accounts: [{ name: 'acc', email_address: 'support@example.com' }],
      signatures: { acc: '<p>-- Підпис</p>' },
      account: 'acc',
      to: 'citizen@example.org',
      cc: '',
      subject: 'Re: Не працює ліхтар',
      files: [],
      templates: [],
      can_print: false,
    })
    form.mockResolvedValue({ to: 'citizen@example.org', subject: 'Re: Не працює ліхтар', content: '<p>Ок</p>' })
    api.sendEmail.mockResolvedValue({ message: 'm2' })
    const wrapper = await mountTimeline()

    await wrapper.find('button[aria-label="Reply"]').trigger('click')
    await flushPromises()

    expect(api.emailComposeContext).toHaveBeenCalledWith('MailCase', 'C-1', 'm1')
    const fields = form.mock.calls[0][0].fields as { fieldname: string; default?: unknown }[]
    expect(fields.map(f => f.fieldname)).toEqual(['to', 'cc', 'bcc', 'subject', 'content'])
    expect(String(fields.find(f => f.fieldname === 'content')?.default)).toContain('Підпис')
    expect(api.sendEmail).toHaveBeenCalledWith('MailCase', 'C-1', expect.objectContaining({
      to: 'citizen@example.org', reply_to: 'm1', email_account: 'acc', files: [],
    }))
    expect(api.getTimeline).toHaveBeenCalledTimes(2) // reloaded after sending
  })

  it('says so when there is no mailbox to send from', async () => {
    api.emailComposeContext.mockResolvedValue({
      accounts: [], signatures: {}, account: null, to: '', cc: '', subject: '', files: [], templates: [], can_print: false,
    })
    const wrapper = await mountTimeline()
    const button = wrapper.findAll('button').find(b => b.text().includes('Email'))
    await button!.trigger('click')
    await flushPromises()
    expect(msgprint).toHaveBeenCalled()
    expect(form).not.toHaveBeenCalled()
  })
})
