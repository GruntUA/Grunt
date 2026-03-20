import client from './client'
import type { GruntDocument, StandardListResponse } from '@/types'

export interface WorkflowTransitionItem {
  action: string
  to_state: string
}

export interface ListParams {
  page?: number
  per_page?: number
  sort?: string
  order?: 'asc' | 'desc'
  search?: string
  fields?: string
  filters?: Record<string, string>
}

export const docsApi = {
  list: async (doctype: string, params: ListParams = {}): Promise<StandardListResponse<GruntDocument>> => {
    const { filters = {}, ...rest } = params
    const filterParams = Object.fromEntries(
      Object.entries(filters).map(([k, v]) => [`filter[${k}]`, v])
    )
    const r = await client.get(`/api/v1/docs/${doctype}`, {
      params: { ...rest, ...filterParams }
    })
    return r.data
  },

  get: (doctype: string, id: string): Promise<GruntDocument> =>
    client.get(`/api/v1/docs/${doctype}/${id}`)
      .then(r => r.data.data),

  create: (doctype: string, data: Record<string, unknown>): Promise<GruntDocument> =>
    client.post(`/api/v1/docs/${doctype}`, data)
      .then(r => r.data.data),

  update: (doctype: string, id: string, data: Record<string, unknown>): Promise<GruntDocument> =>
    client.put(`/api/v1/docs/${doctype}/${id}`, data)
      .then(r => r.data.data),

  delete: (doctype: string, id: string) =>
    client.delete(`/api/v1/docs/${doctype}/${id}`),

  getTransitions: (doctype: string, id: string): Promise<{ data: WorkflowTransitionItem[] }> =>
    client.get(`/api/v1/docs/${doctype}/${id}/transitions`).then(r => r.data),

  applyTransition: (doctype: string, id: string, action: string): Promise<{ success: boolean; data: GruntDocument }> =>
    client.post(`/api/v1/docs/${doctype}/${id}/transition`, { action }).then(r => r.data),
}
