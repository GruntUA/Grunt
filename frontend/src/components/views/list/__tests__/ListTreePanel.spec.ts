import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ListTreePanel from '../ListTreePanel.vue'
import { docsApi } from '@/core/api/docs'
import { ROW_DRAG_MIME } from '@/core/composables/useRowDrag'
import type { ActiveFilter, DocField, DocType } from '@/types'

vi.mock('@/core/api/docs', () => ({
  docsApi: {
    getTreeChildren: vi.fn(),
    getTreeAncestors: vi.fn(),
    moveTreeNode: vi.fn(),
    bulkUpdate: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
}))

const folderDt = {
  name: 'FileFolder',
  is_tree: true,
  tree_parent_field: 'parent_folder',
  tree_title_field: 'folder_name',
  title_field: 'folder_name',
  fields: [],
  permissions: [{ role: 'All', read: true, create: true }],
} as unknown as DocType

vi.mock('@/stores/doctype', () => ({ useDocTypeStore: () => ({ get: async () => folderDt }) }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { roles: ['All'] } }) }))
vi.mock('@tanstack/vue-query', () => ({ useQueryClient: () => ({ invalidateQueries: vi.fn() }) }))
const prompt = vi.fn()
vi.mock('@/core/composables/useDialog', () => ({ useDialog: () => ({ prompt, confirm: vi.fn(async () => true) }) }))
const toast = { success: vi.fn(), error: vi.fn() }
vi.mock('@/core/composables/useToast', () => ({ useToast: () => toast }))

const fileDt = {
  name: 'File',
  fields: [],
  permissions: [{ role: 'All', read: true, write: true }],
} as unknown as DocType
const field = { fieldname: 'folder', fieldtype: 'Link', label: 'Folder', options: 'FileFolder' } as DocField

const roots = [
  { name: 'f1', folder_name: 'Reports', has_children: true },
  { name: 'f2', folder_name: 'Scans', has_children: false },
]

let w: VueWrapper | undefined

function mountPanel(filters: ActiveFilter[] = []) {
  w = mount(ListTreePanel, {
    props: { dt: fileDt, field, filters },
    global: {
      plugins: [createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false })],
      stubs: { RouterLink: true },
    },
  })
  return w
}

function nodeRow(title: string) {
  return w!.findAll('[draggable="true"]').find((r) => r.text().includes(title))!
}

function dropEvent(payload: Record<string, string>) {
  return {
    dataTransfer: {
      types: Object.keys(payload),
      getData: (type: string) => payload[type] ?? '',
    },
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(docsApi.getTreeChildren).mockImplementation(async (_dt, parent) => (parent ? [] : roots))
  vi.mocked(docsApi.getTreeAncestors).mockResolvedValue([])
  vi.mocked(docsApi.bulkUpdate).mockResolvedValue({ updated: 2, errors: [] })
})
afterEach(() => w?.unmount())

describe('ListTreePanel', () => {
  it('lists the root nodes by their title', async () => {
    mountPanel()
    await flushPromises()
    expect(docsApi.getTreeChildren).toHaveBeenCalledWith('FileFolder', null, expect.anything())
    expect(w!.text()).toContain('Reports')
    expect(w!.text()).toContain('Scans')
  })

  it('opening a node sets the list filter, «All» clears it', async () => {
    const other: ActiveFilter = { fieldname: 'content_type', label: 'Type', op: '=', value: 'image/png' }
    mountPanel([other])
    await flushPromises()

    await nodeRow('Reports').findAll('button')[1].trigger('click')
    expect(w!.emitted('update:filters')!.at(-1)![0]).toEqual([
      other,
      expect.objectContaining({ fieldname: 'folder', op: '=', value: 'f1', displayValue: 'Reports' }),
    ])

    await w!.setProps({ filters: [other, { fieldname: 'folder', label: 'Folder', op: '=', value: 'f1' }] })
    await w!.findAll('button').find((b) => b.text() === 'All')!.trigger('click')
    expect(w!.emitted('update:filters')!.at(-1)![0]).toEqual([other])
  })

  it('«Not set» filters rows without a node', async () => {
    mountPanel()
    await flushPromises()
    await w!.findAll('button').find((b) => b.text() === 'Not set')!.trigger('click')
    expect(w!.emitted('update:filters')!.at(-1)![0]).toEqual([
      expect.objectContaining({ fieldname: 'folder', op: 'is not set' }),
    ])
  })

  it('expands a node lazily', async () => {
    mountPanel()
    await flushPromises()
    vi.mocked(docsApi.getTreeChildren).mockResolvedValueOnce([
      { name: 'f3', folder_name: 'Q3', has_children: false },
    ])
    await nodeRow('Reports').findAll('button')[0].trigger('click')
    await flushPromises()
    expect(docsApi.getTreeChildren).toHaveBeenLastCalledWith('FileFolder', 'f1', expect.anything())
    expect(w!.text()).toContain('Q3')
  })

  it('dropping rows on a node re-links them', async () => {
    mountPanel()
    await flushPromises()
    const payload = { [ROW_DRAG_MIME]: JSON.stringify({ doctype: 'File', ids: ['a', 'b'] }) }

    await nodeRow('Scans').trigger('drop', dropEvent(payload))
    await flushPromises()

    expect(docsApi.bulkUpdate).toHaveBeenCalledWith('File', ['a', 'b'], 'folder', 'f2')
    expect(w!.emitted('moved')).toHaveLength(1)
  })

  it('reports rows the server refused to move', async () => {
    vi.mocked(docsApi.bulkUpdate).mockResolvedValueOnce({ updated: 0, errors: ['a: 403: No access'] })
    mountPanel()
    await flushPromises()
    const payload = { [ROW_DRAG_MIME]: JSON.stringify({ doctype: 'File', ids: ['a'] }) }
    await nodeRow('Scans').trigger('drop', dropEvent(payload))
    await flushPromises()
    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('403: No access'))
    expect(w!.emitted('moved')).toBeUndefined()
  })

  it('ignores rows dragged from another DocType', async () => {
    mountPanel()
    await flushPromises()
    const payload = { [ROW_DRAG_MIME]: JSON.stringify({ doctype: 'Employee', ids: ['x'] }) }
    await nodeRow('Scans').trigger('drop', dropEvent(payload))
    await flushPromises()
    expect(docsApi.bulkUpdate).not.toHaveBeenCalled()
  })

  it('dropping a node on another re-parents it', async () => {
    mountPanel()
    await flushPromises()
    await nodeRow('Reports').trigger('drop', dropEvent({ 'application/x-grunt-tree-node': 'f2' }))
    await flushPromises()
    expect(docsApi.moveTreeNode).toHaveBeenCalledWith('FileFolder', 'f2', 'f1')
  })

  it('creates a subfolder under the open node', async () => {
    prompt.mockResolvedValue('New one')
    mountPanel([{ fieldname: 'folder', label: 'Folder', op: '=', value: 'f1' }])
    await flushPromises()
    await w!.find('[title="New folder"]').trigger('click')
    await flushPromises()
    expect(docsApi.create).toHaveBeenCalledWith('FileFolder', { folder_name: 'New one', parent_folder: 'f1' })
  })
})
