// 13x13 range grid where each cell is a mini proportional bar of that hand's
// action mix (GTO+-style range matrix). Modernist dark treatment (design
// handoff 1c): 2px gaps show the ground through as rules, cell fill uses the
// semantic solver palette, the hero's actual combo carries an inset ink ring.
// Reuses expandGroup() pooling so a cell's data matches RangeBreakdownTable.

import { useMemo } from 'react'
import { RANKS, cellHandString } from '../utils/handGrid'
import { solverActionColors, NOT_IN_RANGE } from '../utils/categoricalColors'
import { CanonicalGroup, SpotActionOption } from '../types'
import { expandGroup, DisplayRow } from './RangeBreakdownTable'

interface Props {
  groups: CanonicalGroup[]
  options: SpotActionOption[]
  selectedMembers?: string[]
  /** Click a cell → load that combo (first member) into a detail panel. */
  onSelectCombo?: (combo: string) => void
  cw?: number
  ch?: number
}

export function HandRangeHeatmap({
  groups, options, selectedMembers = [], onSelectCombo, cw = 34, ch = 26,
}: Props) {
  const rowsByHand = useMemo(() => {
    const map = new Map<string, DisplayRow>()
    groups.flatMap(expandGroup).forEach(r => map.set(r.label, r))
    return map
  }, [groups])

  const colors = useMemo(
    () => solverActionColors(options.map(o => o.label)),
    [options],
  )

  return (
    <div className="inline-flex flex-col gap-3">
      <div className="inline-block overflow-x-auto">
        <div className="flex">
          <div style={{ width: 22 }} />
          {RANKS.map(r => (
            <div key={r} style={{ width: cw }}
              className="text-center text-ink-dim text-[10px] font-semibold">{r}</div>
          ))}
        </div>
        <div className="flex flex-col gap-[2px] bg-[rgba(243,242,242,.12)] p-[2px]">
          {RANKS.map((rowRank, ri) => (
            <div key={rowRank} className="flex gap-[2px]">
              <div style={{ width: 22, height: ch }}
                className="flex items-center justify-center text-ink-dim text-[10px] font-semibold">
                {rowRank}
              </div>
              {RANKS.map((colRank, ci) => {
                const handStr = cellHandString(ri, ci, rowRank, colRank)
                const row = rowsByHand.get(handStr)
                const isSelected = row?.members.some(m => selectedMembers.includes(m)) ?? false
                const inRange = !!row && options.some(
                  o => (row.frequencies[String(o.action)] ?? 0) > 0.001)

                if (!inRange) {
                  return (
                    <div
                      key={`${ri}-${ci}`}
                      title={`${handStr} — fold / not in range`}
                      style={{ width: cw, height: ch, backgroundColor: NOT_IN_RANGE }}
                      className="relative flex items-center justify-center"
                    >
                      <span className="text-[9.5px] font-semibold text-ink-muted">{handStr}</span>
                    </div>
                  )
                }

                const tooltip = options
                  .map(o => `${o.label}: ${((row!.frequencies[String(o.action)] ?? 0) * 100).toFixed(0)}%`)
                  .join(' · ')

                return (
                  <div
                    key={`${ri}-${ci}`}
                    title={`${handStr} — ${tooltip}`}
                    onClick={onSelectCombo && row ? () => onSelectCombo(row.members[0]) : undefined}
                    style={{
                      width: cw, height: ch,
                      boxShadow: isSelected ? 'inset 0 0 0 2px #f3f2f2' : undefined,
                    }}
                    className={`relative flex overflow-hidden ${onSelectCombo ? 'cursor-pointer' : ''}`}
                  >
                    {options.map((o, oi) => {
                      const freq = row!.frequencies[String(o.action)] ?? 0
                      if (freq <= 0.001) return null
                      return (
                        <div key={o.action}
                          style={{ width: `${freq * 100}%`, backgroundColor: colors[oi] }} />
                      )
                    })}
                    <span
                      className="absolute inset-0 flex items-center justify-center text-[9.5px] font-semibold text-ground pointer-events-none"
                    >
                      {handStr}
                    </span>
                  </div>
                )
              })}
            </div>
          ))}
        </div>
      </div>
      <div className="flex gap-3 flex-wrap text-[10.5px] font-semibold text-ink-muted">
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 inline-block" style={{ backgroundColor: NOT_IN_RANGE }} />
          Fold / not in range
        </span>
        {options.map((o, oi) => (
          <span key={o.action} className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 inline-block" style={{ backgroundColor: colors[oi] }} />
            {o.label}
          </span>
        ))}
      </div>
    </div>
  )
}
