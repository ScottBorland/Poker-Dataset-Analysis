// Fixed-order categorical palette (dataviz skill reference palette —
// validated: node scripts/validate_palette.js, light mode vs. #ffffff
// surface — CVD-safe adjacent pairs, worst adjacent ΔE 24.2; aqua/yellow/
// magenta sit below 3:1 contrast so anything colored by this palette must
// carry a direct label or tooltip as relief, never color alone).
// Assigned by fixed action index, never re-cycled per value.
export const CATEGORICAL_COLORS = [
  '#2a78d6', // 1 blue
  '#1baf7a', // 2 aqua
  '#eda100', // 3 yellow
  '#008300', // 4 green
  '#4a3aa7', // 5 violet
  '#e34948', // 6 red
  '#e87ba4', // 7 magenta
  '#eb6834', // 8 orange
]

export function actionColor(actionIndex: number): string {
  return CATEGORICAL_COLORS[actionIndex % CATEGORICAL_COLORS.length]
}

// --- Modernist solver palette (design_handoff_poker_flow) -------------------
// Semantic, not categorical: passive actions muted, aggression scales from
// accent-light to accent by bet size. The 13x13 grid, the node action-mix
// bar and the combo panel all colour through this so they agree exactly.
export const NOT_IN_RANGE = '#444141'
const PASSIVE = '#9b9797'          // check / call / fold
const BET_SMALL = '#ff9783'        // accent-light — small bet / raise
const BET_LARGE = '#ff563c'        // accent — large bet / all-in
const BET_MID = '#ff6f52'          // interpolated middle step

/** Colour for one solver action. `label` is the raw TexasSolver label
 *  ('CHECK', 'CALL', 'FOLD', 'BET 3.0', 'RAISE 9.0', 'ALLIN'); `rank` /
 *  `nBets` place a bet within the ordered set of bet sizes at this node. */
export function solverActionColor(label: string, rank = 0, nBets = 1): string {
  const l = label.toUpperCase()
  if (l.startsWith('CHECK') || l.startsWith('CALL') || l.startsWith('FOLD')) return PASSIVE
  if (nBets <= 1) return BET_LARGE
  const t = rank / Math.max(1, nBets - 1)
  return t < 0.34 ? BET_SMALL : t < 0.67 ? BET_MID : BET_LARGE
}

const BET_RE = /^(BET|RAISE|ALLIN)/i

/** Assign each option in a node's action list its solver colour, ranking the
 *  bet/raise options by amount so size maps to hue consistently. */
export function solverActionColors(labels: string[]): string[] {
  const betIdx = labels
    .map((l, i) => ({ l, i, amt: parseFloat((l.match(/[\d.]+/) ?? ['0'])[0]) || 0 }))
    .filter(x => BET_RE.test(x.l))
    .sort((a, b) => a.amt - b.amt)
  const rankOf = new Map(betIdx.map((x, r) => [x.i, r]))
  return labels.map((l, i) =>
    BET_RE.test(l) ? solverActionColor(l, rankOf.get(i) ?? 0, betIdx.length) : solverActionColor(l))
}
