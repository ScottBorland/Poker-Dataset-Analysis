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

export interface FingerprintKey {
  street: string | null
  positions: string | null
  n_players_street: number | null
  pot_type: string | null
  in_position: boolean | null
  facing: string | null
  spr_bucket: string | null
  board_high_card: string | null
  board_paired: boolean | null
  board_monotone: boolean | null
  board_two_tone: boolean | null
  board_connectedness: string | null
}

export interface FingerprintTypeCount {
  key: FingerprintKey
  count: number
}

export interface FingerprintDistributionResponse {
  types: FingerprintTypeCount[]
  total_distinct_types: number
  total_rows: number
}

export interface FingerprintHandRow extends FingerprintKey {
  hand_id: number
  file: string
  player_idx: number
  player_id: string
  position: string | null
  n_players: number
  stack: number | null
  invested: number | null
  winnings: number | null
  net_won: number | null
  venue: string
  big_blind: number | null
  date: string | null
  match_tier?: number
}

export interface FingerprintHandsResponse {
  hands: FingerprintHandRow[]
  total: number
  limit: number
  offset: number
  tier_labels?: string[] | null
}

// --- Solved Spot Explorer ---

export interface SpotRangeInfo {
  position: string
  range_pct: number
}

export interface SpotSummary {
  spot_id: string
  positions: string
  street: string
  board: string
  effective_stack_bb: number
  pot_bb_at_street_start: number
  action_abstraction: string
  bet_sizes_bb: number[]
  n_matching_hands: number
  fingerprint_type: FingerprintKey | null
  source: { venue?: string; generator?: string } | null
  ranges: { oop: SpotRangeInfo; ip: SpotRangeInfo } | null
  oop_range_hands: string[] | null
  ip_range_hands: string[] | null
}

export interface SpotActionOption {
  action: number
  label: string
  next_path: number[] | null
  terminal: boolean
  terminal_type: 'fold' | 'showdown' | null
}

export interface SpotNode {
  path: number[]
  acting_player: number
  options: SpotActionOption[]
}

export interface SpotDetail {
  summary: SpotSummary
  nodes: SpotNode[]
}

export interface NodeRequest {
  action_path: number[]
}

export interface CanonicalGroup {
  canonical_key: [string, string][]
  members: string[]
  frequencies: Record<string, number>
}

export interface NodeDetail {
  path: number[]
  acting_player: number
  options: SpotActionOption[]
  canonical_groups: CanonicalGroup[]
  aggregate: Record<string, number>
}

// --- Fingerprint Hand Replay ---

export interface ReplayStep {
  step: number
  display_step: number
  stacks: number[]
  street_bets: number[]
  pot: number
  total_pot: number
  board: string[]
  hole_cards: Record<string, string[]>
  shown_cards: Record<string, string[]>
  folded: number[]
  street: string
  action_log: string[]
  current_actor: number | null
  hand_over: boolean
}

export interface ReplayResponse {
  hand_id: number
  players: string[]
  positions: Record<string, string>
  big_blind: number | null
  steps: ReplayStep[]
}

// --- Hand Builder ---

export type Street = 'preflop' | 'flop' | 'turn' | 'river'

export interface TableDeriveRequest {
  n_players: number
  stacks_bb: number[]
  hero_seat: number
  preflop_actions: string[]
  flop_actions: string[]
  flop_board: string | null
  turn_actions: string[]
  turn_board: string | null
  river_actions: string[]
  river_board: string | null
  current_street: Street
}

export interface StreetProgressionRow {
  street: Street
  pot_bb: number
  stacks_bb: number[]
  players_in: number[]
}

export interface SolvableStreet {
  street: Street
  positions: string
  pot_bb: number
  effective_stack_bb: number
  board: string | null
  fingerprint_type: FingerprintKey
  hero_is_oop: boolean
}

export interface TableDeriveResponse {
  fingerprint_type: FingerprintKey
  positions: Record<string, string>
  pot_bb_at_street_start: number
  effective_stack_bb: number
  street_progression: StreetProgressionRow[]
  solvable_streets: SolvableStreet[]
}

export interface ScottyStats {
  hands: number
  won_pct: number
  bb_per_100: number
  net_bb: number
}

export interface FingerprintTierStats {
  tier: number
  label: string
  total_hands: number
  avg_pot_bb: number | null
  scotty: ScottyStats | null
}

export interface FingerprintStatsResponse {
  total_hands: number
  avg_pot_bb: number | null
  scotty: ScottyStats | null
  tiers?: FingerprintTierStats[] | null
}

export type SolveStatus = 'not_started' | 'running' | 'exporting' | 'done' | 'failed'

export interface SolveStatusResponse {
  status: SolveStatus
  iterations_done?: number
  iterations_total?: number
  exploitability_pct?: number | null
  engine?: 'texas'
  log_tail?: string[]
  error?: string
}

// --- TexasSolver strategy trees ---

export interface TreePathStep {
  kind: 'action' | 'chance'
  value: string
}

export interface TexasNodeOption {
  action: number
  label: string
  next: 'action' | 'chance' | 'terminal'
  chance_cards: string[] | null
}

// One row of the range-composition breakdown (made-hand or draw category).
// `frequencies` are raw summed action-probabilities (weighted combo counts,
// summing to ~n_combos) — NOT an average like CanonicalGroup.frequencies.
export interface CategoryGroup {
  category: string
  n_combos: number
  frequencies: Record<string, number>
}

export interface TexasNodeResponse {
  node_type: 'action' | 'chance'
  cards?: string[]
  acting_role?: 'oop' | 'ip'
  options?: TexasNodeOption[]
  canonical_groups?: CanonicalGroup[]
  category_groups?: CategoryGroup[]
  board?: string
  aggregate?: Record<string, number>
  hero_frequencies?: Record<string, number> | null
}

export interface SpotLookupResponse {
  spot_id: string | null
  engine: 'texas' | null
  match_tier: number | null
  match_label: string | null
  board: string | null
  street: string | null
}

// --- Line EV (POST /spots/{id}/line-ev) ---

export interface LineEvOption {
  action: number
  label: string
  pretty: string
  ev: number
  solver_freq: number | null
  approx?: boolean
}

export interface LineEvRow {
  street: string
  actor: 'hero' | 'villain'
  chosen_label: string
  chosen_pretty: string
  chosen_ev: number | null
  solver_freq: number | null
  best_label: string | null
  best_pretty: string | null
  best_ev: number | null
  ev_delta: number | null
  approx: boolean
  options: LineEvOption[]
}

export interface LineEvMixItem {
  action: number
  label: string
  pretty: string
  freq: number
}

export interface LineEvCurrentNode {
  actor: 'hero' | 'villain'
  acting_role: 'oop' | 'ip'
  action_mix: LineEvMixItem[]
  hero_action_mix: LineEvMixItem[] | null
  combo_actions: LineEvOption[]
}

export interface LineEvResponse {
  spot_id: string
  hero_role: 'oop' | 'ip'
  hero_combo: string
  board: string
  pot_bb: number
  line: LineEvRow[]
  total_ev_loss: number
  largest_leak: {
    street: string
    chosen_pretty: string
    best_pretty: string | null
    ev_delta: number
    solver_best_freq: number | null
    approx: boolean
  } | null
  current_node: LineEvCurrentNode | null
  combo: {
    combo: string
    hand_class: string
    equity_vs_range: number
    actions: LineEvOption[]
  }
}

export interface HandBuilderExportRequest {
  spot_id: string
  fingerprint_type: FingerprintKey
  street: Street
  positions: string
  effective_stack_bb: number
  pot_bb_at_street_start: number
  board: string | null
  bet_size_fractions: number[]
  n_matching_hands: number
  overwrite?: boolean
}

export interface HandBuilderExportResponse {
  path: string
  spec: Record<string, unknown>
}
