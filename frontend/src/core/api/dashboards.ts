import client from './client'

/** Compute widget data for a Dashboard by name. */
export async function getDashboardData(
  name: string,
  opts?: { dateFrom?: string; dateTo?: string },
): Promise<Record<string, unknown>> {
  const params: Record<string, string> = {}
  if (opts?.dateFrom) params.date_from = opts.dateFrom
  if (opts?.dateTo)   params.date_to   = opts.dateTo
  const r = await client.get(`/api/v1/dashboard-data/${name}`, { params })
  return r.data.data
}
