import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { api } from '../core/api'
import type { DocType } from '../types'

export const useDocTypeStore = defineStore('doctype', () => {
    // Global cache of doctypes to populate sidebar and UI menus
    const { data: docTypes, isLoading, refetch } = useQuery({
        queryKey: ['doctypesList'],
        queryFn: async () => {
            const res = await api.meta.getDocTypes()
            return res.data
        },
        staleTime: 5 * 60 * 1000 // 5 minutes cache
    })

    // Provide a method to get a single DocType details (fetches if needed)
    const getDocTypeDetails = async (name: string): Promise<DocType> => {
        const res = await api.meta.getDocType(name)
        return res.data
    }

    return { docTypes, isLoading, refetch, getDocTypeDetails }
})
