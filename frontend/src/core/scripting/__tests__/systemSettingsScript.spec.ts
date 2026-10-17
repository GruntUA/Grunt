import { describe, it, expect, vi, beforeEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const script = readFileSync(resolve(__dirname, '../../../../../grunt/site/doctypes/SystemSettings/SystemSettings.js'), 'utf8')
const post = vi.fn(async () => ({ data: { data: { queued: true } } }))

vi.mock('@/core/api/client', () => ({
  default: {
    get: async () => ({ data: { data: [{ name: 'grunt:SystemSettings.js', script }] } }),
    post: (...args: unknown[]) => post(...(args as [])),
  },
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { email: 'a@x' } }) }))

import { clearScriptCache, createGruntProxy, executeClientScripts, type FormProxy } from '../executor'

function frm(dirty: boolean) {
  return { is_dirty: dirty, save: vi.fn(async () => {}), doc: {} } as unknown as FormProxy & { save: ReturnType<typeof vi.fn> }
}

describe('SystemSettings «Compress existing images»', () => {
  beforeEach(() => { post.mockClear(); clearScriptCache() })

  it('queues the task after confirmation', async () => {
    const alerts: string[] = []
    const proxy = createGruntProxy({ confirm: async () => true, showAlert: (m) => alerts.push(m) })
    const form = frm(true)
    await executeClientScripts('SystemSettings', 'on_change', form, proxy, 'compress_existing_images')
    expect(post).toHaveBeenCalledWith('/api/v1/method/grunt.storage.images.start_compression', {})
    expect(alerts).toHaveLength(1)
  })

  it('does nothing when not confirmed or for other fields', async () => {
    const proxy = createGruntProxy({ confirm: async () => false })
    await executeClientScripts('SystemSettings', 'on_change', frm(false), proxy, 'compress_existing_images')
    await executeClientScripts('SystemSettings', 'on_change', frm(false), createGruntProxy({ confirm: async () => true }), 'app_name')
    expect(post).not.toHaveBeenCalled()
  })
})
