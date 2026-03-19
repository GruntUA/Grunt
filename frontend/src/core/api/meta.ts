import { apiClient } from './client'
import type { DocType, StandardListResponse, DocTypeSyncResult, StandardResponse } from '../../types'

export const metaApi = {
    getDocTypes: () =>
        apiClient.get<any, StandardListResponse<any>>('/meta/doctypes'),

    getDocType: (name: string) =>
        apiClient.get<any, StandardResponse<DocType>>(`/meta/doctypes/${name}`),

    createDocType: (doctype: any) =>
        apiClient.post<any, StandardResponse<DocType>>('/meta/doctypes', doctype),

    updateDocType: (name: string, doctype: any) =>
        apiClient.put<any, StandardResponse<DocType>>(`/meta/doctypes/${name}`, doctype),

    deleteDocType: (name: string) =>
        apiClient.delete<any, StandardResponse<null>>(`/meta/doctypes/${name}`),

    syncDocType: (name: string) =>
        apiClient.post<any, StandardResponse<DocTypeSyncResult>>(`/meta/doctypes/${name}/sync`),
}
