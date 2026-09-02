import client from './client'
import type { DocType, DocTypeSummary, IndexHint } from '@/types'

export interface DocTypeSaveResult {
  data: DocType
  hints: IndexHint[]
  exported_to: string | null
}

export interface ValidatorInfo { name: string; label: string; field_types: string[] }

export interface DocTypeTableInfo {
  doctype: string
  table_name: string
  dialect: string
  exists: boolean
  row_count: number | null
  table_bytes: number | null
  index_bytes: number | null
  total_bytes: number | null
  reclaimable_bytes: number | null
  reclaim_scope: 'table' | 'database' | null
  size_supported: boolean
  dead_tuples?: number
}

export interface DocTypeCompactResult {
  doctype: string
  table_name: string
  dialect: string
  scope: 'table' | 'database'
  command?: string
  before_bytes: number | null
  after_bytes: number | null
  freed_bytes: number | null
}

export const metaApi = {
  list: (module?: string): Promise<DocTypeSummary[]> =>
    client.get('/api/v1/method/grunt.api.v1.meta.list_doctypes', { params: { module } })
      .then(r => r.data.data),

  get: (name: string): Promise<DocType> =>
    client.get('/api/v1/method/grunt.api.v1.meta.get_doctype', { params: { name } })
      .then(r => r.data.data),

  listValidators: (): Promise<ValidatorInfo[]> =>
    client.get('/api/v1/method/grunt.api.v1.meta.list_validators')
      .then(r => r.data.data),

  create: (dt: DocType): Promise<DocTypeSaveResult> =>
    client.post('/api/v1/method/grunt.api.v1.meta.save_doctype', { doctype_data: { ...dt, __is_new: true } })
      .then(r => ({ data: r.data.data, hints: [], exported_to: null })),

  update: (dt: DocType): Promise<DocTypeSaveResult> =>
    client.post('/api/v1/method/grunt.api.v1.meta.save_doctype', { doctype_data: dt })
      .then(r => ({ data: r.data.data, hints: [], exported_to: null })),

  delete: (name: string) =>
    client.post('/api/v1/method/grunt.api.v1.meta.delete_doctype', { name }),

  sync: (name: string) =>
    client.post('/api/v1/method/grunt.api.v1.meta.sync_doctype', { name })
      .then(r => r.data.data),

  tableInfo: (name: string): Promise<DocTypeTableInfo> =>
    client.get('/api/v1/method/grunt.api.v1.meta.table_info', { params: { name } })
      .then(r => r.data.data),

  compactTable: (name: string): Promise<DocTypeCompactResult> =>
    client.post('/api/v1/method/grunt.api.v1.meta.compact_table', { name })
      .then(r => r.data.data),
}
