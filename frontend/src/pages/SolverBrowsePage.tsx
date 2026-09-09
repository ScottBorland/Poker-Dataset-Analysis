// Solver browse (screen 1c, entry point). Lists every stored TexasSolver
// solution under cfr_solver/results/ so the Solver tab is reachable on its
// own — not only via the Hand Builder's "Open in solver" handoff. Picking a
// row synthesises the SolverOpenArgs the Solver view needs and opens it.

import { useEffect, useMemo, useState } from 'react'
import { AppChrome, AppView } from '../components/AppChrome'
import { Btn, SectionLabel, Badge, PlayingCard } from '../components/modernist'
import { getSpotsApi } from '../utils/api'
import { SpotSummary, FingerprintKey } from '../types'
import { SolverOpenArgs } from './HandBuilderPage'

interface Props {
  view: AppView
  onView: (v: AppView) => void
  onOpen: (args: SolverOpenArgs) => void
}

const STREET_ORDER: Record<string, number> = { flop: 0, turn: 1, river: 2 }

function splitPositions(positions: string): [string, string] {
  const [a, b] = positions.split('_vs_')
  return [a ?? 'IP', b ?? 'OOP']
}

/** Build the args the Solver view expects from a stored spot summary. The
 *  fingerprint's own perspective (in_position) picks which seat is "hero";
 *  when a spec predates the fingerprint_type field we fall back to OOP. */
export function argsFromSpot(s: SpotSummary): SolverOpenArgs {
  const [ipFromPos, oopFromPos] = splitPositions(s.positions)
  const ipPos = s.ranges?.ip.position ?? ipFromPos
  const oopPos = s.ranges?.oop.position ?? oopFromPos

  const fp: FingerprintKey = s.fingerprint_type ?? {
    street: s.street,
    positions: s.positions,
    n_players_street: 2,
    pot_type: null,
    in_position: null,
    facing: null,
    spr_bucket: null,
    board_high_card: s.board?.[1] ?? null,
    board_paired: null,
    board_monotone: null,
    board_two_tone: null,
    board_connectedness: null,
  }

  const heroIsOop = fp.in_position !== true // subject is hero; default OOP if unknown
  return {
    spotId: s.spot_id,
    heroCombo: null,
    heroIsOop,
    heroLabel: heroIsOop ? oopPos : ipPos,
    villainLabel: heroIsOop ? ipPos : oopPos,
    storedBoard: s.board,
    fingerprintType: fp,
  }
}

function boardCards(board: string): string[] {
  return board.match(/../g) ?? []
}

export default function SolverBrowsePage({ view, onView, onOpen }: Props) {
  const [spots, setSpots] = useState<SpotSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getSpotsApi()
      .then(res => { if (!cancelled) setSpots(res) })
      .catch(err => { if (!cancelled) setError(String(err)) })
    return () => { cancelled = true }
  }, [])

  const rows = useMemo(() => {
    if (!spots) return []
    return [...spots].sort((a, b) => {
      const s = (STREET_ORDER[a.street] ?? 9) - (STREET_ORDER[b.street] ?? 9)
      if (s !== 0) return s
      return (b.n_matching_hands ?? 0) - (a.n_matching_hands ?? 0)
    })
  }, [spots])

  return (
    <div className="flex flex-col h-full w-full overflow-hidden bg-ground text-ink">
      <AppChrome view={view} onView={onView} />

      <div className="flex items-center gap-3 px-5 py-4 border-b-2 border-divider-strong shrink-0">
        <span className="font-extrabold text-[13px] tracking-brand uppercase">Solutions</span>
        <span className="text-[11px] text-ink-muted">
          {spots ? `${spots.length} stored solve${spots.length === 1 ? '' : 's'}` : 'Loading…'}
        </span>
        <div className="ml-auto">
          <Btn onClick={() => onView('builder')}>Build a new spot</Btn>
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-auto px-5 py-4">
        {error && <div className="text-[12px] text-accent-light">{error}</div>}

        {spots && spots.length === 0 && !error && (
          <div className="flex flex-col items-start gap-3 text-[12.5px] text-ink-muted max-w-[440px]">
            <div>
              No solved spots yet. Play a hand to a heads-up flop in the Hand
              Builder and run a solve — finished solves show up here.
            </div>
            <Btn variant="accent" onClick={() => onView('builder')}>Go to hand builder</Btn>
          </div>
        )}

        {rows.length > 0 && (
          <div
            className="grid gap-x-4 items-center text-[10px] font-extrabold tracking-label
              uppercase text-ink-muted border-b-2 border-divider-strong pb-2"
            style={{ gridTemplateColumns: '1.4fr 68px 1.5fr 84px 84px 92px 96px' }}
          >
            <span>Matchup</span>
            <span>Street</span>
            <span>Board</span>
            <span className="text-right">Pot</span>
            <span className="text-right">Eff. stack</span>
            <span className="text-right">Ranges IP/OOP</span>
            <span className="text-right">Real hands</span>
          </div>
        )}

        {rows.map(s => {
          const [ipFromPos, oopFromPos] = splitPositions(s.positions)
          const ipPos = s.ranges?.ip.position ?? ipFromPos
          const oopPos = s.ranges?.oop.position ?? oopFromPos
          const heroIsOop = (s.fingerprint_type?.in_position ?? false) !== true
          const heroPos = heroIsOop ? oopPos : ipPos
          const villPos = heroIsOop ? ipPos : oopPos
          return (
            <button
              key={s.spot_id}
              onClick={() => onOpen(argsFromSpot(s))}
              className="w-full grid gap-x-4 items-center text-left py-3 border-b border-divider-light
                hover:bg-[rgba(243,242,242,.06)] focus-visible:outline focus-visible:outline-2
                focus-visible:outline-accent"
              style={{ gridTemplateColumns: '1.4fr 68px 1.5fr 84px 84px 92px 96px' }}
            >
              <span className="flex flex-col gap-0.5">
                <span className="text-[13px] font-semibold text-ink">
                  {heroPos} <span className="text-ink-muted">(hero, {heroIsOop ? 'OOP' : 'IP'})</span> vs {villPos}
                </span>
                <span className="text-[10px] text-ink-dim tracking-seat uppercase">
                  {(s.fingerprint_type?.pot_type ?? 'srp').toUpperCase()}
                  {s.source?.venue ? ` · ${s.source.venue}` : ''}
                </span>
              </span>

              <span><Badge tone="outline">{s.street}</Badge></span>

              <span className="flex gap-[3px]">
                {boardCards(s.board).map((c, i) => (
                  <PlayingCard key={i} card={c} w={24} h={34} />
                ))}
              </span>

              <span className="text-right text-[12px] font-semibold tabular-nums text-ink">
                {s.pot_bb_at_street_start.toFixed(1)} BB
              </span>
              <span className="text-right text-[12px] font-semibold tabular-nums text-ink-muted">
                {s.effective_stack_bb.toFixed(0)} BB
              </span>
              <span className="text-right text-[12px] font-semibold tabular-nums text-ink-muted">
                {s.ranges ? `${s.ranges.ip.range_pct}% / ${s.ranges.oop.range_pct}%` : '—'}
              </span>
              <span className="text-right text-[12px] font-semibold tabular-nums text-ink-muted">
                {s.n_matching_hands || '—'}
              </span>
            </button>
          )
        })}

        {rows.length > 0 && (
          <div className="pt-4">
            <SectionLabel className="text-ink-muted">
              Pick a row to walk its solved tree and score a line
            </SectionLabel>
          </div>
        )}
      </div>
    </div>
  )
}
