import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import type { DocType } from '@/types'
import { useFormDocumentView } from '../useFormDocumentView'

function setup() {
  const form = ref<Record<string, unknown>>({ name: 'X', title: 'old' })
  const runOnChange = vi.fn()
  const dt = ref({
    name: 'Demo',
    fields: [
      { fieldname: 'title', fieldtype: 'Data' },
      { fieldname: 'test_connection', fieldtype: 'Button' },
    ],
  } as unknown as DocType)
  const view = useFormDocumentView({ id: 'X', dt, document: ref({ name: 'X' }), form, runOnChange })
  return { form, runOnChange, view }
}

describe('useFormDocumentView.onFormUpdate', () => {
  it('a Button click fires on_change without touching the document', () => {
    const { form, runOnChange, view } = setup()
    view.onFormUpdate({ ...form.value, test_connection: 123 })
    expect(runOnChange).toHaveBeenCalledWith('test_connection')
    expect(form.value).toEqual({ name: 'X', title: 'old' })

    view.onFormUpdate({ ...form.value, test_connection: 124 })
    expect(runOnChange).toHaveBeenCalledTimes(2) // every click counts
  })

  it('a field change is stored and fires on_change once', () => {
    const { form, runOnChange, view } = setup()
    view.onFormUpdate({ ...form.value, title: 'new' })
    expect(form.value.title).toBe('new')
    expect(runOnChange).toHaveBeenCalledExactlyOnceWith('title')
  })
})
