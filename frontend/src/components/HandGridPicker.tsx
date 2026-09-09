// Single-hand exact-card picker styled like the query builder's HoleCardGrid
// (13x13, pairs on the diagonal, suited above, offsuit below), but resolves
// each cell to one concrete exact card pair (needed for the CFR solver's
// per-exact-hand strategy lookup) via a deterministic suit assignment that
// skips cards already used by the board or the other hand.

import { useMemo } from 'react'
import { RANKS, CellType, cellType, cellHandString } from '../utils/handGrid'

const SUITS = ['s', 'h', 'd', 'c']

function assignExactCards(rank1: string, rank2: string, type: CellType, disabled: Set<string>): [string, string] | null {
  if (type === 'suited') {
    for (const s of SUITS) {
      const c1 = rank1 + s
      const c2 = rank2 + s
      if (!disabled.has(c1) && !disabled.has(c2)) return [c1, c2]
    }
    return null
  }
  if (type === 'pair') {
    for (let i = 0; i < SUITS.length; i++) {
      for (let j = i + 1; j < SUITS.length; j++) {
        const c1 = rank1 + SUITS[i]
        const c2 = rank1 + SUITS[j]
        if (!disabled.has(c1) && !disabled.has(c2)) return [c1, c2]
      }
    }
    return null
  }
  // offsuit
  for (const s1 of SUITS) {
    for (const s2 of SUITS) {
      if (s1 === s2) continue
      const c1 = rank1 + s1
      const c2 = rank2 + s2
      if (!disabled.has(c1) && !disabled.has(c2)) return [c1, c2]
    }
  }
  return null
}

interface Props {
  value: [string | null, string | null]
  onChange: (value: [string, string]) => void
  disabledCards?: string[]
  label?: string
  /** Canonical hand strings (e.g. "AKs") assumed in this seat's range for
   *  the spot. Out-of-range cells are still clickable (so a user can
   *  deliberately explore "what if" outside the assumed range) but are
   *  visually muted. Omit/null to skip this distinction entirely. */
  inRangeHands?: string[] | null
}

export function HandGridPicker({ value, onChange, disabledCards = [], label, inRangeHands }: Props) {
  const disabled = useMemo(() => new Set(disabledCards), [disabledCards])
  const inRange = useMemo(() => (inRangeHands ? new Set(inRangeHands) : null), [inRangeHands])

  const selectedCell = useMemo(() => {
    if (!value[0] || !value[1]) return null
    const i1 = RANKS.indexOf(value[0][0])
    const i2 = RANKS.indexOf(value[1][0])
    if (i1 === -1 || i2 === -1) return null
    if (i1 === i2) return `${i1}-${i1}`
    const suited = value[0][1] === value[1][1]
    return suited ? `${Math.min(i1, i2)}-${Math.max(i1, i2)}` : `${Math.max(i1, i2)}-${Math.min(i1, i2)}`
  }, [value])

  const CELL = 24

  return (
    <div className="inline-block bg-gray-900 border border-gray-700 rounded-lg p-2">
      {label && <div className="text-xs text-gray-300 font-semibold mb-1">{label}</div>}
      <div className="flex">
        <div style={{ width: CELL }} />
        {RANKS.map(r => (
          <div key={r} style={{ width: CELL }} className="text-center text-gray-500 text-[10px] font-mono">{r}</div>
        ))}
      </div>
      {RANKS.map((rowRank, ri) => (
        <div key={rowRank} className="flex">
          <div style={{ width: CELL, height: CELL }} className="flex items-center justify-center text-gray-500 text-[10px] font-mono">
            {rowRank}
          </div>
          {RANKS.map((colRank, ci) => {
            const type = cellType(ri, ci)
            const isSelected = selectedCell === `${ri}-${ci}`
            const assigned = assignExactCards(rowRank, colRank, type, disabled)
            const isUnavailable = assigned === null
            const handStr = cellHandString(ri, ci, rowRank, colRank)
            const isOutOfRange = inRange != null && !inRange.has(handStr)

            const baseColor = isSelected
              ? 'bg-amber-500 text-black border-amber-400'
              : isUnavailable
              ? 'bg-gray-950 text-gray-700 border-gray-900 cursor-not-allowed'
              : isOutOfRange
              ? 'bg-gray-900 text-gray-600 border-gray-800 border-dashed hover:bg-gray-800'
              : type === 'pair'
              ? 'bg-gray-700 text-gray-200 border-gray-600 hover:bg-gray-600'
              : type === 'suited'
              ? 'bg-blue-950 text-blue-300 border-blue-900 hover:bg-blue-900'
              : 'bg-gray-800 text-gray-400 border-gray-700 hover:bg-gray-700'

            const title = !assigned
              ? 'Unavailable (clashes with board or other hand)'
              : isOutOfRange
              ? `${handStr} — outside this seat's assumed range for this spot`
              : assigned.join(' ')

            return (
              <button
                key={`${ri}-${ci}`}
                title={title}
                disabled={isUnavailable}
                onClick={() => assigned && onChange(assigned)}
                style={{ width: CELL, height: CELL }}
                className={`border text-[10px] font-mono transition-colors ${baseColor}`}
              >
                {ri === ci ? rowRank : ri < ci ? 's' : 'o'}
              </button>
            )
          })}
        </div>
      ))}
    </div>
  )
}
