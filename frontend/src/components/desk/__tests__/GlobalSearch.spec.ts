import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { useWorkspaceStore } from '@/stores/workspace'
import type { Workspace } from '@/core/api/workspace'
import GlobalSearch from '../GlobalSearch.vue'

// ── Mocks ─────────────────────────────────────────────────────────────────

// vi.hoisted ensures these are available inside vi.mock factories (which are hoisted)
const { mockPush, mockSearch } = vi.hoisted(() => ({
  mockPush: vi.fn(),
  mockSearch: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
}))

vi.mock('@/core/api/workspace', () => ({
  workspaceApi: {
    search: mockSearch,
    list: vi.fn().mockResolvedValue([]),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    getCounts: vi.fn().mockResolvedValue({}),
  },
}))

// Stub icon components to avoid SVG rendering issues in jsdom
vi.mock('lucide-vue-next', () => ({
  Search:     { template: '<svg data-icon="search" />' },
  ArrowRight: { template: '<svg data-icon="arrow-right" />' },
  FileText:   { template: '<svg data-icon="file-text" />' },
  AppWindow:  { template: '<svg data-icon="app-window" />' },
}))

// ── Fixtures ───────────────────────────────────────────────────────────────

function makeWorkspace(overrides: Partial<Workspace> = {}): Workspace {
  return {
    name: 'crm',
    label: 'CRM',
    app: 'crm',
    icon: '📋',
    color: '#2D6A4F',
    description: 'CRM додаток',
    sequence: 0,
    is_hidden: false,
    roles: '',
    items: [],
    ...overrides,
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────

async function typeQuery(wrapper: ReturnType<typeof mount>, text: string) {
  const input = wrapper.find('input')
  await input.setValue(text)
  // setValue triggers input + change; manually focus to set isOpen
  await input.trigger('focus')
}

// ── Tests ──────────────────────────────────────────────────────────────────

describe('GlobalSearch', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    const pinia = createPinia()
    setActivePinia(pinia)
    mockPush.mockClear()
    mockSearch.mockReset()
    mockSearch.mockResolvedValue([])
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  function mountComponent() {
    return mount(GlobalSearch)
  }

  // ── Rendering ────────────────────────────────────────────────────────────

  describe('початковий рендер', () => {
    it('рендерить поле вводу', () => {
      const wrapper = mountComponent()
      expect(wrapper.find('input[type="text"]').exists()).toBe(true)
    })

    it('показує правильний placeholder', () => {
      const wrapper = mountComponent()
      expect(wrapper.find('input').attributes('placeholder')).toBe('Пошук по додатках та документах...')
    })

    it('не показує дропдаун при старті', () => {
      const wrapper = mountComponent()
      // overlay div has v-if="isOpen && query.trim()"
      expect(wrapper.find('[class*="absolute top-full"]').exists()).toBe(false)
    })

    it('показує бейдж клавіатурного скорочення', () => {
      const wrapper = mountComponent()
      expect(wrapper.find('kbd').exists()).toBe(true)
    })
  })

  // ── Focus ────────────────────────────────────────────────────────────────

  describe('поведінка при фокусі', () => {
    it('фокус на інпуті відкриває isOpen', async () => {
      const wrapper = mountComponent()
      await wrapper.find('input').trigger('focus')
      // isOpen = true BUT query is still empty, so overlay should NOT render
      expect(wrapper.find('[class*="absolute top-full"]').exists()).toBe(false)
    })

    it('дропдаун видимий коли є запит і інпут у фокусі', async () => {
      const wrapper = mountComponent()
      await wrapper.find('input').trigger('focus')
      await wrapper.find('input').setValue('crm')
      expect(wrapper.find('[class*="absolute top-full"]').exists()).toBe(true)
    })

    it('дропдаун прихований поки запит порожній', async () => {
      const wrapper = mountComponent()
      await wrapper.find('input').trigger('focus')
      await wrapper.find('input').setValue('   ')
      expect(wrapper.find('[class*="absolute top-full"]').exists()).toBe(false)
    })
  })

  // ── Workspace filtering ───────────────────────────────────────────────────

  describe('фільтрація воркспейсів', () => {
    it('порожній запит не показує воркспейси', async () => {
      const wrapper = mountComponent()
      const store = useWorkspaceStore()
      store.workspaces = [makeWorkspace()]
      await wrapper.find('input').trigger('focus')
      expect(wrapper.text()).not.toContain('Додатки')
    })

    it('фільтрує воркспейс за label', async () => {
      const wrapper = mountComponent()
      const store = useWorkspaceStore()
      store.workspaces = [makeWorkspace({ label: 'CRM Система', name: 'crm' })]
      await wrapper.find('input').trigger('focus')
      await wrapper.find('input').setValue('crm')
      expect(wrapper.text()).toContain('CRM Система')
      expect(wrapper.text()).toContain('Додатки')
    })

    it('фільтрує воркспейс за name', async () => {
      const wrapper = mountComponent()
      const store = useWorkspaceStore()
      store.workspaces = [makeWorkspace({ label: 'Бухгалтерія', name: 'finance' })]
      await wrapper.find('input').trigger('focus')
      await wrapper.find('input').setValue('finance')
      expect(wrapper.text()).toContain('Бухгалтерія')
    })

    it('фільтрація без урахування регістру', async () => {
      const wrapper = mountComponent()
      const store = useWorkspaceStore()
      store.workspaces = [makeWorkspace({ label: 'CRM', name: 'crm' })]
      await wrapper.find('input').trigger('focus')
      await wrapper.find('input').setValue('CRM')
      expect(wrapper.text()).toContain('CRM')
    })

    it('не показує невідповідні воркспейси', async () => {
      const wrapper = mountComponent()
      const store = useWorkspaceStore()
      store.workspaces = [makeWorkspace({ label: 'Склад', name: 'warehouse' })]
      await wrapper.find('input').trigger('focus')
      await wrapper.find('input').setValue('crm')
      expect(wrapper.text()).not.toContain('Склад')
    })

    it('клік по воркспейсу викликає router.push з правильним шляхом', async () => {
      const wrapper = mountComponent()
      const store = useWorkspaceStore()
      store.workspaces = [makeWorkspace({ name: 'hrm', label: 'HRM' })]
      await wrapper.find('input').trigger('focus')
      await wrapper.find('input').setValue('hrm')
      const btn = wrapper.findAll('button').find(b => b.text().includes('HRM'))
      await btn!.trigger('click')
      expect(mockPush).toHaveBeenCalledWith('/hrm')
    })

    it('клік по воркспейсу закриває дропдаун', async () => {
      const wrapper = mountComponent()
      const store = useWorkspaceStore()
      store.workspaces = [makeWorkspace({ name: 'crm', label: 'CRM' })]
      await wrapper.find('input').trigger('focus')
      await wrapper.find('input').setValue('crm')
      const btn = wrapper.findAll('button').find(b => b.text().includes('CRM'))
      await btn!.trigger('click')
      expect(wrapper.find('[class*="absolute top-full"]').exists()).toBe(false)
    })
  })

  // ── API search ────────────────────────────────────────────────────────────

  describe('пошук документів (з debounce)', () => {
    it('не викликає API при порожньому запиті', async () => {
      const wrapper = mountComponent()
      await wrapper.find('input').trigger('focus')
      await wrapper.find('input').setValue('   ')
      vi.advanceTimersByTime(400)
      expect(mockSearch).not.toHaveBeenCalled()
    })

    it('не викликає API до закінчення debounce (300ms)', async () => {
      const wrapper = mountComponent()
      await wrapper.find('input').trigger('focus')
      await wrapper.find('input').setValue('договір')
      vi.advanceTimersByTime(299)
      expect(mockSearch).not.toHaveBeenCalled()
    })

    it('викликає API після 300ms debounce', async () => {
      const wrapper = mountComponent()
      await wrapper.find('input').trigger('focus')
      await wrapper.find('input').setValue('договір')
      vi.advanceTimersByTime(300)
      expect(mockSearch).toHaveBeenCalledOnce()
      expect(mockSearch).toHaveBeenCalledWith('договір')
    })

    it('повторна зміна запиту скасовує попередній debounce', async () => {
      const wrapper = mountComponent()
      await wrapper.find('input').trigger('focus')
      await wrapper.find('input').setValue('до')
      vi.advanceTimersByTime(100)
      await wrapper.find('input').setValue('договір')
      vi.advanceTimersByTime(300)
      expect(mockSearch).toHaveBeenCalledOnce()
      expect(mockSearch).toHaveBeenCalledWith('договір')
    })

    it('показує результати документів після успішної відповіді API', async () => {
      mockSearch.mockResolvedValue([
        { doctype: 'Договір', id: '1', name: 'ДОГ-001', display_title: 'Договір №1' },
      ])
      const wrapper = mountComponent()
      await wrapper.find('input').trigger('focus')
      await wrapper.find('input').setValue('договір')
      vi.advanceTimersByTime(300)
      await flushPromises()
      expect(wrapper.text()).toContain('Документи')
      expect(wrapper.text()).toContain('Договір №1')
      expect(wrapper.text()).toContain('Договір')
    })

    it('показує стан завантаження під час пошуку', async () => {
      let resolve: (v: unknown[]) => void
      mockSearch.mockReturnValue(new Promise(r => { resolve = r }))
      const wrapper = mountComponent()
      await wrapper.find('input').trigger('focus')
      await wrapper.find('input').setValue('тест')
      vi.advanceTimersByTime(300)
      await flushPromises()
      expect(wrapper.text()).toContain('Шукаю')
      resolve!([])
    })

    it('при помилці API результати залишаються порожніми', async () => {
      mockSearch.mockRejectedValue(new Error('Network error'))
      const wrapper = mountComponent()
      await wrapper.find('input').trigger('focus')
      await wrapper.find('input').setValue('помилка')
      vi.advanceTimersByTime(300)
      await flushPromises()
      expect(wrapper.text()).not.toContain('Документи')
    })
  })

  // ── Navigation – documents ────────────────────────────────────────────────

  describe('навігація до документів', () => {
    it('клік по документу з відповідним воркспейсом будує правильний шлях', async () => {
      const ws = makeWorkspace({
        name: 'contracts',
        label: 'Договори',
        items: [{ section: '', type: 'DocType', label: 'Договір', icon: '', link_to: 'Договір', show_count: false, show_new_btn: false, roles: '', sequence: 0, count_filters: '' }],
      })
      mockSearch.mockResolvedValue([
        { doctype: 'Договір', id: '42', name: 'ДОГ-001', display_title: 'Договір №1' },
      ])
      const wrapper = mountComponent()
      const store = useWorkspaceStore()
      store.workspaces = [ws]
      await wrapper.find('input').trigger('focus')
      await wrapper.find('input').setValue('договір')
      vi.advanceTimersByTime(300)
      await flushPromises()
      const btn = wrapper.findAll('button').find(b => b.text().includes('Договір №1'))
      await btn!.trigger('click')
      expect(mockPush).toHaveBeenCalledWith('/contracts/list/Договір/42')
    })

    it('клік по документу без відповідного воркспейсу використовує порожній префікс', async () => {
      mockSearch.mockResolvedValue([
        { doctype: 'Акт', id: '7', name: 'АКТ-007', display_title: 'Акт №7' },
      ])
      const wrapper = mountComponent()
      useWorkspaceStore().workspaces = []
      await wrapper.find('input').trigger('focus')
      await wrapper.find('input').setValue('акт')
      vi.advanceTimersByTime(300)
      await flushPromises()
      const btn = wrapper.findAll('button').find(b => b.text().includes('Акт №7'))
      await btn!.trigger('click')
      expect(mockPush).toHaveBeenCalledWith('/list/Акт/7')
    })

    it('клік по документу закриває дропдаун та очищає запит', async () => {
      mockSearch.mockResolvedValue([
        { doctype: 'Акт', id: '1', name: 'АКТ-001', display_title: 'Акт №1' },
      ])
      const wrapper = mountComponent()
      await wrapper.find('input').trigger('focus')
      await wrapper.find('input').setValue('акт')
      vi.advanceTimersByTime(300)
      await flushPromises()
      const btn = wrapper.findAll('button').find(b => b.text().includes('Акт №1'))
      await btn!.trigger('click')
      expect((wrapper.find('input').element as HTMLInputElement).value).toBe('')
      expect(wrapper.find('[class*="absolute top-full"]').exists()).toBe(false)
    })
  })

  // ── No results ────────────────────────────────────────────────────────────

  describe('стан "нічого не знайдено"', () => {
    it('показує повідомлення коли немає ні воркспейсів ні документів', async () => {
      mockSearch.mockResolvedValue([])
      const wrapper = mountComponent()
      useWorkspaceStore().workspaces = []
      await wrapper.find('input').trigger('focus')
      await wrapper.find('input').setValue('невідомо')
      vi.advanceTimersByTime(300)
      await flushPromises()
      expect(wrapper.text()).toContain('Нічого не знайдено')
      expect(wrapper.text()).toContain('невідомо')
    })

    it('не показує повідомлення поки іде пошук', async () => {
      let resolve: (v: unknown[]) => void
      mockSearch.mockReturnValue(new Promise(r => { resolve = r }))
      const wrapper = mountComponent()
      await wrapper.find('input').trigger('focus')
      await wrapper.find('input').setValue('тест')
      vi.advanceTimersByTime(300)
      await flushPromises()
      expect(wrapper.text()).not.toContain('Нічого не знайдено')
      resolve!([])
    })
  })

  // ── Close behavior ────────────────────────────────────────────────────────

  describe('закриття', () => {
    it('Escape закриває дропдаун', async () => {
      const wrapper = mountComponent()
      await wrapper.find('input').trigger('focus')
      await wrapper.find('input').setValue('тест')
      expect(wrapper.find('[class*="absolute top-full"]').exists()).toBe(true)
      await wrapper.find('input').trigger('keydown', { key: 'Escape' })
      expect(wrapper.find('[class*="absolute top-full"]').exists()).toBe(false)
    })

    it('Escape очищає запит', async () => {
      const wrapper = mountComponent()
      await wrapper.find('input').trigger('focus')
      await wrapper.find('input').setValue('тест')
      await wrapper.find('input').trigger('keydown', { key: 'Escape' })
      expect((wrapper.find('input').element as HTMLInputElement).value).toBe('')
    })

    it('клік на backdrop закриває дропдаун', async () => {
      const wrapper = mountComponent()
      await wrapper.find('input').trigger('focus')
      await wrapper.find('input').setValue('тест')
      const backdrop = wrapper.find('.fixed.inset-0')
      expect(backdrop.exists()).toBe(true)
      await backdrop.trigger('click')
      expect(wrapper.find('[class*="absolute top-full"]').exists()).toBe(false)
    })

    it('після закриття результати очищаються', async () => {
      mockSearch.mockResolvedValue([
        { doctype: 'Договір', id: '1', name: 'ДОГ-001', display_title: 'Договір №1' },
      ])
      const wrapper = mountComponent()
      await wrapper.find('input').trigger('focus')
      await wrapper.find('input').setValue('договір')
      vi.advanceTimersByTime(300)
      await flushPromises()
      expect(wrapper.text()).toContain('Договір №1')
      await wrapper.find('input').trigger('keydown', { key: 'Escape' })
      // After close, results are cleared — reopen with same text would show nothing until API
      await wrapper.find('input').trigger('focus')
      await wrapper.find('input').setValue('договір')
      // No API called yet (debounce not fired)
      expect(wrapper.text()).not.toContain('Документи')
    })
  })

  // ── Global keyboard shortcut ──────────────────────────────────────────────

  describe('глобальний хоткей', () => {
    it('Ctrl+K відкриває пошук', async () => {
      const wrapper = mountComponent()
      const event = new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, bubbles: true })
      const preventDefaultSpy = vi.spyOn(event, 'preventDefault')
      document.dispatchEvent(event)
      await flushPromises()
      expect(preventDefaultSpy).toHaveBeenCalled()
    })

    it('Meta+K відкриває пошук', async () => {
      const wrapper = mountComponent()
      const event = new KeyboardEvent('keydown', { key: 'k', metaKey: true, bubbles: true })
      const preventDefaultSpy = vi.spyOn(event, 'preventDefault')
      document.dispatchEvent(event)
      await flushPromises()
      expect(preventDefaultSpy).toHaveBeenCalled()
    })

    it('звичайне натискання клавіші не відкриває пошук', async () => {
      const wrapper = mountComponent()
      const event = new KeyboardEvent('keydown', { key: 'a', bubbles: true })
      const preventDefaultSpy = vi.spyOn(event, 'preventDefault')
      document.dispatchEvent(event)
      await flushPromises()
      expect(preventDefaultSpy).not.toHaveBeenCalled()
    })
  })

  // ── Cleanup ───────────────────────────────────────────────────────────────

  describe('очищення', () => {
    it('знімає глобальний обробник при unmount', async () => {
      const removeSpy = vi.spyOn(document, 'removeEventListener')
      const wrapper = mountComponent()
      wrapper.unmount()
      expect(removeSpy).toHaveBeenCalledWith('keydown', expect.any(Function))
    })
  })
})
