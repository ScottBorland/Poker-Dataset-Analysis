import {
  ApiFilter,
  StatsData,
  FingerprintKey,
  FingerprintDistributionResponse,
  FingerprintHandsResponse,
  SpotSummary,
  SpotDetail,
  NodeRequest,
  NodeDetail,
  ReplayResponse,
  TableDeriveRequest,
  TableDeriveResponse,
  HandBuilderExportRequest,
  HandBuilderExportResponse,
  FingerprintStatsResponse,
  SolveStatusResponse,
  TreePathStep,
  TexasNodeResponse,
  SpotLookupResponse,
  LineEvResponse,
} from '../types'

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

export async function getFingerprintDistributionApi(
  street: string | null,
  limit = 30,
  venue: string | null = null
): Promise<FingerprintDistributionResponse> {
  const res = await fetch(`${BASE}/fingerprints/distribution`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ street, limit, venue }),
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function getFingerprintHandsApi(
  types: FingerprintKey[],
  limit = 500,
  offset = 0,
  venue: string | null = null,
  fuzzy = false,
  maxTier = 4
): Promise<FingerprintHandsResponse> {
  const res = await fetch(`${BASE}/fingerprints/hands`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ types, limit, offset, venue, fuzzy, max_tier: maxTier }),
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function getSpotsApi(): Promise<SpotSummary[]> {
  const res = await fetch(`${BASE}/spots`)
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function getSpotDetailApi(spotId: string): Promise<SpotDetail> {
  const res = await fetch(`${BASE}/spots/${encodeURIComponent(spotId)}`)
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function getSpotNodeApi(spotId: string, req: NodeRequest): Promise<NodeDetail> {
  const res = await fetch(`${BASE}/spots/${encodeURIComponent(spotId)}/node`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail ?? `API error: ${res.status}`)
  }
  return res.json()
}

export async function getHandReplayApi(handId: number, file: string, venue: string): Promise<ReplayResponse> {
  const res = await fetch(`${BASE}/hands/${handId}/replay`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file, venue }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail ?? `API error: ${res.status}`)
  }
  return res.json()
}

export async function deriveHandBuilderApi(req: TableDeriveRequest): Promise<TableDeriveResponse> {
  const res = await fetch(`${BASE}/hand-builder/derive`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail ?? `API error: ${res.status}`)
  }
  return res.json()
}

export async function getFingerprintStatsApi(
  types: FingerprintKey[],
  venue: string | null = '888poker',
  fuzzy = false,
  maxTier = 4
): Promise<FingerprintStatsResponse> {
  const res = await fetch(`${BASE}/fingerprints/stats`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ types, venue, fuzzy, max_tier: maxTier }),
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function startSolveApi(
  spotId: string,
  opts: { accuracy?: number; maxIteration?: number } = {}
): Promise<{ status: string; iterations: number; engine: string }> {
  const res = await fetch(`${BASE}/solve/${encodeURIComponent(spotId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      accuracy: opts.accuracy ?? 0.3,
      max_iteration: opts.maxIteration ?? 200,
    }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail ?? `API error: ${res.status}`)
  }
  return res.json()
}

export async function getTexasTreeNodeApi(
  spotId: string,
  path: TreePathStep[],
  heroCombo: string | null = null
): Promise<TexasNodeResponse> {
  const res = await fetch(`${BASE}/spots/${encodeURIComponent(spotId)}/tree-node`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, hero_combo: heroCombo }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail ?? `API error: ${res.status}`)
  }
  return res.json()
}

export async function getLineEvApi(
  spotId: string,
  path: TreePathStep[],
  heroCombo: string
): Promise<LineEvResponse> {
  const res = await fetch(`${BASE}/spots/${encodeURIComponent(spotId)}/line-ev`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, hero_combo: heroCombo }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail ?? `API error: ${res.status}`)
  }
  return res.json()
}

export async function lookupSolvedSpotApi(
  fingerprintType: FingerprintKey,
  maxTier = 4
): Promise<SpotLookupResponse> {
  const res = await fetch(`${BASE}/spots/lookup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fingerprint_type: fingerprintType, max_tier: maxTier }),
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function getSolveStatusApi(spotId: string): Promise<SolveStatusResponse> {
  const res = await fetch(`${BASE}/solve/${encodeURIComponent(spotId)}/status`)
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function exportSpotSpecApi(req: HandBuilderExportRequest): Promise<HandBuilderExportResponse> {
  const res = await fetch(`${BASE}/hand-builder/export-spot`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const err = new Error(body?.detail ?? `API error: ${res.status}`) as Error & { status?: number }
    err.status = res.status
    throw err
  }
  return res.json()
}
