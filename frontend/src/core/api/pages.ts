import client from './client'

export interface AppPage {
  name: string
  route: string
  title?: string | null
  icon?: string | null
  component?: string | null
  app?: string | null
  sidebar_section?: string | null
  sidebar_order?: number | null
  is_default_home?: boolean
}

export async function fetchPages(): Promise<AppPage[]> {
  const r = await client.get('/api/v1/method/grunt.api.v1.pages.list_pages')
  return r.data.data ?? []
}

/** Compute widget data for a Page by name. */
export async function getPageData(
  name: string,
  opts?: { dateFrom?: string; dateTo?: string },
): Promise<Record<string, unknown>> {
  const params: Record<string, string> = {}
  if (opts?.dateFrom) params.date_from = opts.dateFrom
  if (opts?.dateTo)   params.date_to   = opts.dateTo
  const r = await client.get(`/api/v1/page-data/${name}`, { params })
  return r.data.data
}
