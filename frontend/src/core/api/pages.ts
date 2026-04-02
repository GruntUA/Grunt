import client from './client'

export interface AppPage {
  id: string
  route: string
  title: string
  icon: string | null
  component: string
  app: string
  sidebar_section: string | null
  sidebar_order: number
  is_default_home: boolean
}

export async function fetchPages(): Promise<AppPage[]> {
  const r = await client.get('/api/v1/pages/')
  return r.data?.data ?? []
}
