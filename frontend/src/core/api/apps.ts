import client from './client'

export interface GruntApp {
    id: string
    name: string
    title: string
    version: string
    modules: string[]
    installed_at?: string
}

export const appsApi = {
    list: async (): Promise<GruntApp[]> => {
        const response = await client.get('/api/v1/method/grunt.api.v1.apps.list_apps')
        return response.data.data || []
    },

    addModule: async (appName: string, moduleName: string): Promise<GruntApp> => {
        const response = await client.post('/api/v1/method/grunt.api.v1.apps.add_module', {
            name: appName,
            module: moduleName
        })
        return response.data.data
    },
}
