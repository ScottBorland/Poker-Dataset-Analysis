export interface ApiFilter {
  type: string
  value: unknown
}

export interface StatsData {
  total_hands: number
  showdown_pct: number
  avg_pot_bb: number
  message?: string
  scotty_hands?: number | null
  scotty_won_pct?: number | null
  scotty_bb_per_100?: number | null
}

export interface StatsNodeData extends Record<string, unknown> {
  stats: StatsData | null
  loading: boolean
  error: string | null
  hasHoleCards: boolean
}

export interface FilterNodeData extends Record<string, unknown> {
  type: string
  value: unknown
}
