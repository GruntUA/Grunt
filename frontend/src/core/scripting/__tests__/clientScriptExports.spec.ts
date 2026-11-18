import { describe, it, expect, vi, beforeEach } from 'vitest'

const scripts = [
  { name: 'app:Exported.js', script: 'export function on_load(frm) { frm.calls.push("exported") }\nexport const X = 1' },
  { name: 'app:Plain.js', script: 'function on_load(frm) { frm.calls.push("plain") }' },
  { name: 'app:Async.js', script: 'export async function on_load(frm) { frm.calls.push("async") }' },
]

vi.mock('@/core/api/client', () => ({
  default: { get: async () => ({ data: { data: scripts } }) },
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { email: 'a@x' } }) }))

import { clearScriptCache, createGruntProxy, executeClientScripts, stripExports, type FormProxy } from '../executor'

describe('client scripts written as modules', () => {
  beforeEach(() => clearScriptCache())

  it('drops only a top-level export before a declaration', () => {
    expect(stripExports('export function a() {}\nexport async function b() {}\nexport const c = 1\nexport class D {}'))
      .toBe('function a() {}\nasync function b() {}\nconst c = 1\nclass D {}')
    // Inside code or not before a declaration: left as is.
    expect(stripExports('  export function a() {}')).toBe('  export function a() {}')
    expect(stripExports('const s = "export function x"')).toBe('const s = "export function x"')
  })

  it('runs exported, plain and async hooks alike', async () => {
    const frm = { calls: [] as string[] } as unknown as FormProxy & { calls: string[] }
    await executeClientScripts('Note', 'on_load', frm, createGruntProxy({}))
    expect(frm.calls).toEqual(['exported', 'plain', 'async'])
  })
})
