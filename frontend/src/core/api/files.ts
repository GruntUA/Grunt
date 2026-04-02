import client from './client'

export interface FileItem {
    id: string
    url: string
    filename: string
    content_type: string
    size_bytes: number
    created_at: string | null
    uploaded_by: string
}

export const filesApi = {
    list: async (params?: { limit?: number; offset?: number; search?: string }): Promise<{ data: FileItem[], total: number }> => {
        const res = await client.get('/api/v1/files', { params })
        return res.data
    },

    upload: async (file: File): Promise<FileItem> => {
        const formData = new FormData()
        formData.append('file', file)
        const res = await client.post('/api/v1/files', formData, {
            headers: { 'Content-Type': 'multipart/form-data' }
        })
        return res.data.data
    },

    delete: async (id: string): Promise<void> => {
        await client.delete(`/api/v1/files/${id}`)
    }
}
