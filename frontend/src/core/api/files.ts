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
    list: async (params?: { limit?: number; page?: number; filters?: any; search?: string }): Promise<{ items: FileItem[], total: number }> => {
        const res = await client.get('/api/v1/method/grunt.core.doctypes.file.file.get_list', { params })
        return res.data.data
    },

    upload: async (file: File): Promise<FileItem> => {
        const formData = new FormData()
        formData.append('file', file)
        const res = await client.post('/api/v1/method/grunt.core.doctypes.file.file.upload', formData, {
            headers: { 'Content-Type': 'multipart/form-data' }
        })
        return res.data.data
    },

    getById: async (id: string): Promise<FileItem | null> => {
        const res = await client.get(`/api/v1/docs/File/${id}`)
        const doc = res.data.data
        return doc ? {
            id: doc.id,
            url: doc.file_url,
            filename: doc.file_name,
            content_type: doc.content_type,
            size_bytes: doc.file_size,
            created_at: doc.created_at,
            uploaded_by: doc.uploaded_by,
        } : null
    },

    delete: async (id: string): Promise<void> => {
        await client.post('/api/v1/method/grunt.core.doctypes.file.file.remove', { file_id: id })
    }
}
