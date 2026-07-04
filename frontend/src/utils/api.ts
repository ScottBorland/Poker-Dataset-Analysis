import { ApiFilter, StatsData } from '../types'

const BASE = ''

export async function runQueryApi(filters: ApiFilter[]): Promise<StatsData> {
  const res = await fetch(`${BASE}/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filters }),
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function getSqlApi(filters: ApiFilter[]): Promise<string> {
  const res = await fetch(`${BASE}/sql`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filters }),
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  const data = await res.json()
  return data.sql
}
