import client from './client'
import type { DocType, DocTypeSummary } from '@/types'

export const metaApi = {
  list: (module?: string): Promise<DocTypeSummary[]> =>
    client.get('/api/v1/meta/doctypes', { params: { module } })
      .then(r => r.data),

  get: (name: string): Promise<DocType> =>
    client.get(`/api/v1/meta/doctypes/${name}`)
      .then(r => r.data),

  create: (dt: DocType): Promise<DocType> =>
    client.post('/api/v1/meta/doctypes', dt)
      .then(r => r.data),

  update: (dt: DocType): Promise<DocType> =>
    client.put(`/api/v1/meta/doctypes/${dt.name}`, dt)
      .then(r => r.data),

  delete: (name: string) =>
    client.delete(`/api/v1/meta/doctypes/${name}`),

  sync: (name: string) =>
    client.post(`/api/v1/meta/doctypes/${name}/sync`)
      .then(r => r.data),
}
