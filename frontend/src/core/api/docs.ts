import { apiClient } from './client'
import type { StandardListResponse, StandardResponse } from '../../types'

export const docsApi = {
    getList: (doctype: string, params?: any) =>
        apiClient.get<any, StandardListResponse<any>>(`/docs/${doctype}`, { params }),

    getOne: (doctype: string, id: string) =>
        apiClient.get<any, StandardResponse<any>>(`/docs/${doctype}/${id}`),

    create: (doctype: string, data: any) =>
        apiClient.post<any, StandardResponse<any>>(`/docs/${doctype}`, data),

    update: (doctype: string, id: string, data: any) =>
        apiClient.put<any, StandardResponse<any>>(`/docs/${doctype}/${id}`, data),

    delete: (doctype: string, id: string) =>
        apiClient.delete<any, StandardResponse<null>>(`/docs/${doctype}/${id}`),
}
