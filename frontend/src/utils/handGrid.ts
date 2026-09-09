// Shared 13x13 starting-hand grid layout (pairs on the diagonal, suited
// above, offsuit below) — used by HandGridPicker (input) and
// HandRangeHeatmap (display) so both stay pixel- and label-compatible.

export const RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']

export type CellType = 'pair' | 'suited' | 'offsuit'

export function cellType(row: number, col: number): CellType {
  if (row === col) return 'pair'
  if (row < col) return 'suited'
  return 'offsuit'
}

// Canonical hand string for a cell, e.g. "AKs", "AKo", "AA" — matches
// cfr_solver/hand_ranking.py's format exactly (used to look up range
// membership) and src/api.py's _canonical_class() (used to key
// canonical_groups from the solver), so this format must stay in sync
// with both.
export function cellHandString(row: number, col: number, rowRank: string, colRank: string): string {
  if (row === col) return rowRank + colRank
  if (row < col) return rowRank + colRank + 's'
  return colRank + rowRank + 'o'
}
