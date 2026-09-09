import { CanonicalGroup, SpotActionOption } from '../types'

// Standard poker high-to-low rank order, used both for "which rank comes
// first in the label" (Q2o, not 2Qo) and to detect pairs.
const RANK_ORDER = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']
const rankIndex = (r: string) => RANK_ORDER.indexOf(r)

export interface DisplayRow {
  key: string
  label: string
  members: string[]
  frequencies: Record<string, number>
}

// The backend's canonical_key only tracks whether each card matches the
// board's single "flush suit" (see export_strategy.py) — two cards sharing
// some *other* suit are tagged identically to two cards of different other
// suits, since neither can complete a flush on this board. That's the
// statistically-correct pooling for the solve, but for display we still
// want the familiar suited/offsuit split, so re-derive it here from the
// raw member combo strings (member[1] and member[3] are each card's suit
// character) rather than from the pooled canonical_key.
export function expandGroup(g: CanonicalGroup): DisplayRow[] {
  const [c1, c2] = g.canonical_key
  const groupKey = JSON.stringify(g.canonical_key)
  const pair = c1[0] === c2[0]

  // Flop/turn solves canonicalize by board-fixing suit isomorphism, so the
  // key carries real suit letters instead of BIG/OTHER tags. Different
  // suited groups (e.g. flush-draw suit vs pooled empty suits) get distinct
  // keys with the same rank label — disambiguate with the canonical suits.
  const realSuits = g.canonical_key.every(c => 'hdcs'.includes(c[1]))
  if (realSuits && !pair) {
    const hiFirst = rankIndex(c1[0]) <= rankIndex(c2[0]) ? [c1, c2] : [c2, c1]
    const suited = c1[1] === c2[1]
    const label = suited
      ? `${hiFirst[0][0]}${hiFirst[1][0]}s (${c1[1]})`
      : `${hiFirst[0][0]}${hiFirst[1][0]}o (${hiFirst[0][1]}${hiFirst[1][1]})`
    return [{ key: groupKey, label, members: g.members, frequencies: g.frequencies }]
  }
  if (realSuits && pair) {
    return [{
      key: groupKey,
      label: `${c1[0]}${c2[0]} (${c1[1]}${c2[1]})`,
      members: g.members,
      frequencies: g.frequencies,
    }]
  }

  const bigCount = g.canonical_key.filter(c => c[1] === 'BIG').length

  if (pair) {
    return [{
      key: groupKey,
      label: `${c1[0]}${c2[0]}${bigCount > 0 ? ' (incl. flush-suit card)' : ''}`,
      members: g.members,
      frequencies: g.frequencies,
    }]
  }

  const hi = rankIndex(c1[0]) <= rankIndex(c2[0]) ? c1[0] : c2[0]
  const lo = hi === c1[0] ? c2[0] : c1[0]

  // bigCount 1 (exactly one card matches the flush suit) can only happen
  // for offsuit combos: two cards sharing a suit always share the same
  // BIG/OTHER tag. bigCount 2 can only happen for suited (flush-suited)
  // combos, by the same logic.
  if (bigCount === 1) {
    return [{ key: groupKey, label: `${hi}${lo}o (1 card flush-suited)`, members: g.members, frequencies: g.frequencies }]
  }
  if (bigCount === 2) {
    return [{ key: groupKey, label: `${hi}${lo}s (flush suit)`, members: g.members, frequencies: g.frequencies }]
  }

  // bigCount 0: raw members may still be suited or offsuit with each other
  // (just not in the board's flush suit) — split for display, sharing the
  // same (pooled) frequencies since they're strategically identical here.
  const suited = g.members.filter(m => m[1] === m[3])
  const offsuit = g.members.filter(m => m[1] !== m[3])
  const rows: DisplayRow[] = []
  if (suited.length) rows.push({ key: `${groupKey}-s`, label: `${hi}${lo}s`, members: suited, frequencies: g.frequencies })
  if (offsuit.length) rows.push({ key: `${groupKey}-o`, label: `${hi}${lo}o`, members: offsuit, frequencies: g.frequencies })
  return rows
}

interface Props {
  groups: CanonicalGroup[]
  options: SpotActionOption[]
  sortByAction: number
  selectedMembers?: string[]
  onSelectCombo?: (combo: string) => void
}

export function RangeBreakdownTable({ groups, options, sortByAction, selectedMembers = [], onSelectCombo }: Props) {
  const rows = groups.flatMap(expandGroup).sort(
    (a, b) => (b.frequencies[String(sortByAction)] ?? 0) - (a.frequencies[String(sortByAction)] ?? 0)
  )
  const totalMembers = groups.reduce((s, g) => s + g.members.length, 0)

  return (
    <div className="flex flex-col border border-gray-200 rounded-md overflow-hidden">
      <div className="overflow-auto" style={{ maxHeight: 260 }}>
        <table className="min-w-full text-xs">
          <thead className="sticky top-0 bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-2 py-1 text-left font-semibold text-gray-600">Hand class</th>
              <th className="px-2 py-1 text-left font-semibold text-gray-600"># combos</th>
              {options.map(o => (
                <th key={o.action} className="px-2 py-1 text-left font-semibold text-gray-600 whitespace-nowrap">
                  {o.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(row => {
              const isSelected = row.members.some(m => selectedMembers.includes(m))
              return (
                <tr
                  key={row.key}
                  onClick={onSelectCombo ? () => onSelectCombo(row.members[0]) : undefined}
                  className={`${isSelected ? 'bg-amber-100' : 'bg-white'} ${
                    onSelectCombo ? 'cursor-pointer hover:bg-indigo-50' : ''
                  }`}
                >
                  <td className="px-2 py-1 whitespace-nowrap">{row.label}</td>
                  <td className="px-2 py-1 tabular-nums">{row.members.length}</td>
                  {options.map(o => (
                    <td key={o.action} className="px-2 py-1 tabular-nums">
                      {((row.frequencies[String(o.action)] ?? 0) * 100).toFixed(0)}%
                    </td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className="px-2 py-1 text-[11px] text-gray-400 border-t border-gray-100 bg-gray-50">
        {totalMembers} raw combos across {rows.length} rows
        {onSelectCombo && ' — click a row to see that hand on the table'}
      </div>
    </div>
  )
}
