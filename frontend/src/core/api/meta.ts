import client from './client'
import type { DocType, DocTypeSummary, IndexHint } from '@/types'

export interface DocTypeSaveResult {
  data: DocType
  hints: IndexHint[]
  exported_to: string | null
}

export const metaApi = {
  list: (module?: string): Promise<DocTypeSummary[]> =>
    client.get('/api/v1/method/grunt.api.v1.meta.list_doctypes', { params: { module } })
      .then(r => r.data.data),

  get: (name: string): Promise<DocType> =>
    client.get('/api/v1/method/grunt.api.v1.meta.get_doctype', { params: { name } })
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
}
