import client from './client'

/** Compute widget data for a Dashboard by name. */
export async function getDashboardData(name: string): Promise<Record<string, unknown>> {
  const r = await client.get(`/api/v1/dashboard-data/${name}`)
  return r.data.data
}
