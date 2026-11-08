import { describe, it, expect, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import i18n from '@/plugins/i18n'
import type { FormTour as Tour, TourView } from '@/core/api/workspace'
import FormTour from '../FormTour.vue'

let w: VueWrapper | undefined
afterEach(() => { w?.unmount(); document.body.innerHTML = '' })

/** An element the tour can point at, with a size (jsdom measures everything as 0). */
function target(attrs: Record<string, string>) {
  const el = document.createElement('div')
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v)
  el.getBoundingClientRect = () =>
    ({ top: 10, left: 20, width: 100, height: 30, bottom: 40, right: 120, x: 20, y: 10 }) as DOMRect
  el.scrollIntoView = () => {}
  document.body.appendChild(el)
  return el
}

async function mountTour(view: TourView, steps: Tour['steps'], reveal?: (f: string) => void) {
  const tour: Tour = { name: 't', title: 'Tour', auto_start: false, taken: false, steps }
  w = mount(FormTour, { props: { tour, view, reveal }, global: { plugins: [i18n] }, attachTo: document.body })
  await flushPromises()
  return w
}

const spotlight = () => document.body.querySelector('.rounded-md.pointer-events-none')

describe('FormTour', () => {
  it('points at a list column or quick filter by fieldname', async () => {
    target({ 'data-column': 'status' })
    await mountTour('List', [{ title: 'Status', fieldname: 'status' }])
    expect(spotlight()).not.toBeNull()
  })

  it('finds a quick filter when the column is hidden', async () => {
    target({ 'data-quick-filter': 'region' })
    await mountTour('List', [{ title: 'Region', fieldname: 'region' }])
    expect(spotlight()).not.toBeNull()
  })

  it('a form step points at the field and opens its tab', async () => {
    target({ 'data-fieldname': 'status' })
    const revealed: string[] = []
    await mountTour('Form', [{ title: 'Status', fieldname: 'status' }], (f) => revealed.push(f))
    expect(spotlight()).not.toBeNull()
    expect(revealed).toEqual(['status'])
  })

  it('a list column is not a form field', async () => {
    target({ 'data-column': 'status' })
    await mountTour('Form', [{ title: 'Status', fieldname: 'status' }], () => {})
    expect(spotlight()).toBeNull() // centred card instead
  })

  it('an element step uses its selector in any view', async () => {
    target({ 'data-tour-target': 'search' })
    await mountTour('List', [{ title: 'Search', element: '[data-tour-target=search]' }])
    expect(spotlight()).not.toBeNull()
  })
})
