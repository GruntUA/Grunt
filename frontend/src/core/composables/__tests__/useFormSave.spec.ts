import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

vi.mock('@/core/scripting/executor', () => ({ clearScriptCache: vi.fn() }))
vi.mock('@/stores/app', () => ({ useAppStore: () => ({ markStale: vi.fn() }) }))

import { useFormSave } from '../useFormSave'

function rejectWith(status: number, code: string) {
  return Object.assign(new Error('save failed'), {
    response: { status, data: { error: { code, message: 'server says no' } } },
  })
}

function setup(error: unknown) {
  const toast = { success: vi.fn(), error: vi.fn(), warning: vi.fn() }
  const queryClient = { invalidateQueries: vi.fn() }
  const reload = vi.fn(async () => {})
  const { handleSave } = useFormSave({
    doctype: 'Role',
    id: 'Clerk',
    dt: ref(null),
    form: ref({ name: 'Clerk' }),
    validationErrors: ref({}),
    save: () => Promise.reject(error),
    reload,
    runScriptEvent: async () => true,
    validateForm: () => true,
    focusFirstError: vi.fn(),
    markAllowLeave: vi.fn(),
    finishLinkCreate: () => false,
    queryClient: queryClient as never,
    dtStore: { invalidate: vi.fn() },
    router: {} as never,
    toast,
  })
  return { handleSave, toast, reload }
}

describe('form save conflicts', () => {
  it('a stale document (someone saved it meanwhile) offers a reload', async () => {
    const { handleSave, toast, reload } = setup(rejectWith(409, 'STALE_DOCUMENT'))
    await handleSave()

    expect(toast.error).not.toHaveBeenCalled()
    expect(toast.warning).toHaveBeenCalledOnce()
    const [message, , opts] = toast.warning.mock.calls[0]
    expect(message).toBe('server says no')
    expect(opts.duration).toBe(Infinity)

    opts.action.onClick()
    expect(reload).toHaveBeenCalledOnce()
  })

  it('any other conflict (a duplicate value) is a plain error', async () => {
    const { handleSave, toast } = setup(rejectWith(409, 'HTTP_409'))
    await handleSave()

    expect(toast.warning).not.toHaveBeenCalled()
    expect(toast.error).toHaveBeenCalledWith('server says no')
  })
})
