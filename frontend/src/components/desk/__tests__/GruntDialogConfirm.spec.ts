import { describe, it, expect, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import i18n from '@/plugins/i18n'
import GruntDialog from '../GruntDialog.vue'
import { useDialog } from '@/core/composables/useDialog'

let w: VueWrapper | undefined
afterEach(() => { w?.unmount(); document.body.innerHTML = '' })

async function ask(button: (buttons: HTMLButtonElement[]) => HTMLButtonElement) {
  w = mount(GruntDialog, { attachTo: document.body, global: { plugins: [i18n] } })
  const answer = useDialog().confirm('Sure?')
  await flushPromises()
  const buttons = [...document.body.querySelectorAll<HTMLButtonElement>('[role="alertdialog"] button')]
  button(buttons).click()
  await flushPromises()
  return answer
}

describe('GruntDialog confirm', () => {
  it('resolves true on the confirm button', async () => {
    expect(await ask((b) => b.at(-1)!)).toBe(true)
  })

  it('resolves false on Cancel', async () => {
    expect(await ask((b) => b[0])).toBe(false)
  })
})
