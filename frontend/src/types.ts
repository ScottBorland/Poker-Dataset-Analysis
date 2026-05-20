export interface ApiFilter {
  type: string
  value: unknown
}

export interface PositionStat {
  position: string
  hands: number
  net_won: number
  bb_per_100: number
}

export interface TopPlayer {
  player_id: string
  hands: number
  net_won: number
}

export interface StatsData {
  total_hands: number
  showdown_pct: number
  avg_pot_bb: number
  by_position: PositionStat[]
  top_players: TopPlayer[]
  message?: string
  scotty_hands?: number
  scotty_won_pct?: number | null
  scotty_bb_per_100?: number | null
}

export interface StatsNodeData extends Record<string, unknown> {
  stats: StatsData | null
  loading: boolean
  error: string | null
}

export interface FilterNodeData extends Record<string, unknown> {
  type: string
  value: unknown
}
