// Hand Builder (design_handoff_poker_flow, screen 1b) — an interactive poker
// table restyled onto the Modernist dark ground. Same state and API calls as
// before; new visual structure: header bar, diagrammatic seat grid, action
// bar, two-column action log, right rail (Situation / Similar real hands /
// Solve spot). Walking a solved line now happens on the dedicated Solver
// view (screen 1c) — the "view solution" buttons navigate there.

import { useEffect, useMemo, useRef, useState } from 'react'
import { AppChrome, AppView } from '../components/AppChrome'
import { BuilderTable, BuilderSeat } from '../components/BuilderTable'
import { CardPickerModal } from '../components/CardPickerModal'
import { HandLookupPanel } from '../components/HandLookupPanel'
import { Btn, Segmented, SectionLabel, Badge } from '../components/modernist'
import {
  buildTable, legalActions, totalPot, toDerivePayload, positionLabel,
  streetsReached, TableEvent, Street,
} from '../utils/tableEngine'
import {
  deriveHandBuilderApi, getFingerprintStatsApi, exportSpotSpecApi,
  startSolveApi, getSolveStatusApi, lookupSolvedSpotApi,
} from '../utils/api'
import {
  TableDeriveResponse, FingerprintStatsResponse, FingerprintKey,
  SolvableStreet, SolveStatus, SpotLookupResponse,
} from '../types'

export interface SolverOpenArgs {
  spotId: string
  heroCombo: string | null
  heroIsOop: boolean
  heroLabel: string
  villainLabel: string
  storedBoard?: string | null
  fingerprintType: FingerprintKey
}

const BET_FRACTION_CHOICES = [0.33, 0.5, 0.66, 0.75, 1.0, 1.25, 1.5, 2.0]
const TIER_CHOICES = [
  { value: 0, label: 'Exact' },
  { value: 1, label: '+Board' },
  { value: 2, label: '+SPR' },
  { value: 3, label: '+Facing' },
  { value: 4, label: 'Any position' },
]
const QUICK_SIZES: { label: string; frac: number }[] = [
  { label: '⅓ pot', frac: 1 / 3 },
  { label: '½ pot', frac: 0.5 },
  { label: '⅔ pot', frac: 2 / 3 },
  { label: 'pot', frac: 1.0 },
]
const STREET_DISPLAY_ORDER: Record<string, number> = { flop: 0, turn: 1, river: 2 }

type Modal =
  | { type: 'hole'; seatIdx: number }
  | { type: 'board'; street: Exclude<Street, 'preflop'> }
  | null

interface SolveJob {
  street: Street
  spotId: string
  heroIsOop: boolean
  positions: string
  fingerprintType: FingerprintKey
  status: SolveStatus | 'exporting_spec'
  done: number
  total: number
  exploitability?: number | null
  error?: string
}

function villainFromPositions(positions: string, heroPos: string): string {
  const parts = positions.split('_vs_')
  return parts.find(p => p !== heroPos) ?? 'Villain'
}

function fingerprintSlug(fp: unknown): string {
  const s = JSON.stringify(fp)
  let h = 5381
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0
  return Math.abs(h).toString(36)
}

function formatAction(action: string, nPlayers: number): string {
  const [pTag, verb, amount] = action.split(' ')
  const pos = positionLabel(nPlayers, parseInt(pTag.slice(1), 10))
  if (verb === 'f') return `${pos} folds`
  if (verb === 'cc') return `${pos} checks/calls`
  return `${pos} bets to ${amount} BB`
}

function seatOfAction(action: string): number {
  return parseInt(action.split(' ')[0].slice(1), 10)
}

function boardTexture(fp: FingerprintKey | undefined): string {
  if (!fp?.board_high_card) return 'Board'
  const suit = fp.board_monotone ? 'monotone' : fp.board_two_tone ? 'two-tone' : 'rainbow'
  return `Board · ${fp.board_high_card}-high ${suit}${fp.board_paired ? ' paired' : ''}`
}

interface Props {
  view: AppView
  onView: (v: AppView) => void
  onOpenSolver: (args: SolverOpenArgs) => void
}

export default function HandBuilderPage({ view, onView, onOpenSolver }: Props) {
  const [nPlayers, setNPlayers] = useState(6)
  const [stackBB, setStackBB] = useState(100)
  const [events, setEvents] = useState<TableEvent[]>([])
  const [holeCards, setHoleCards] = useState<Record<number, [string, string]>>({})
  const [heroSeat, setHeroSeat] = useState<number | null>(6)
  const [modal, setModal] = useState<Modal>(null)
  const [betInput, setBetInput] = useState('')

  const table = useMemo(() => buildTable({ nPlayers, stackBB }, events), [nPlayers, stackBB, events])
  const legal = legalActions(table)
  const pot = totalPot(table)

  function resetHand(newN = nPlayers, newStack = stackBB) {
    setNPlayers(newN)
    setStackBB(newStack)
    setEvents([])
    setHoleCards({})
    setHeroSeat(newN)
    setModal(null)
    setBetInput('')
    setDerive(null)
    setStats(null)
    setJobs([])
  }

  const awaiting = table.awaitingBoard
  useEffect(() => {
    if (awaiting && awaiting !== 'preflop' && !table.handOver) {
      setModal({ type: 'board', street: awaiting })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [awaiting])

  const usedCards = useMemo(() => {
    const cards: string[] = []
    for (const pair of Object.values(holeCards)) cards.push(...pair)
    for (const b of [table.boards.flop, table.boards.turn, table.boards.river]) {
      if (b) for (let i = 0; i + 1 < b.length; i += 2) cards.push(b.slice(i, i + 2))
    }
    return cards
  }, [holeCards, table.boards])

  // --- Derived situation (debounced) ---
  const [derive, setDerive] = useState<TableDeriveResponse | null>(null)
  const [deriveError, setDeriveError] = useState<string | null>(null)
  const derivePayload = heroSeat != null
    ? toDerivePayload(table, heroSeat, Array(nPlayers).fill(stackBB))
    : null
  const payloadKey = JSON.stringify(derivePayload)
  useEffect(() => {
    if (!derivePayload) { setDerive(null); setDeriveError(null); return }
    const t = setTimeout(() => {
      deriveHandBuilderApi(derivePayload)
        .then(res => { setDerive(res); setDeriveError(null) })
        .catch(err => { setDerive(null); setDeriveError(String(err)) })
    }, 400)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [payloadKey])

  // --- Similar-hands stats (auto-fetch per fingerprint, debounced) ---
  const [stats, setStats] = useState<FingerprintStatsResponse | null>(null)
  const [statsLoading, setStatsLoading] = useState(false)
  const [maxTier, setMaxTier] = useState(2)
  const fpKey = JSON.stringify(derive?.fingerprint_type ?? null)
  useEffect(() => {
    if (!derive) { setStats(null); setStatsLoading(false); return }
    let cancelled = false
    setStats(null)
    setStatsLoading(true)
    const t = setTimeout(() => {
      getFingerprintStatsApi([derive.fingerprint_type], '888poker', true, 4)
        .then(res => { if (!cancelled) setStats(res) })
        .catch(() => { if (!cancelled) setStats(null) })
        .finally(() => { if (!cancelled) setStatsLoading(false) })
    }, 1200)
    return () => { cancelled = true; clearTimeout(t) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fpKey])

  // --- Stored-solution lookup (automatic per fingerprint) ---
  const [lookup, setLookup] = useState<SpotLookupResponse | null>(null)
  useEffect(() => {
    setLookup(null)
    if (!derive) return
    let cancelled = false
    lookupSolvedSpotApi(derive.fingerprint_type)
      .then(res => { if (!cancelled) setLookup(res) })
      .catch(() => { if (!cancelled) setLookup(null) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fpKey])

  // --- Solve jobs (TexasSolver: full 3-street DCFR) ---
  const [solveMode, setSolveMode] = useState<'final' | 'path'>('path')
  const [fractions, setFractions] = useState<number[]>([0.33, 0.5, 0.66, 0.75, 1.0, 2.0])
  const [maxIteration, setMaxIteration] = useState(200)
  const [jobs, setJobs] = useState<SolveJob[]>([])
  const jobsRef = useRef(jobs)
  jobsRef.current = jobs

  async function launchSolves() {
    if (!derive || derive.solvable_streets.length === 0) return
    const targets: SolvableStreet[] = solveMode === 'final'
      ? [derive.solvable_streets[derive.solvable_streets.length - 1]]
      : derive.solvable_streets
    const newJobs: SolveJob[] = targets.map(t => ({
      street: t.street,
      spotId: `builder_${t.street}_${fingerprintSlug(t.fingerprint_type)}`,
      heroIsOop: t.hero_is_oop,
      positions: t.positions,
      fingerprintType: t.fingerprint_type,
      status: 'exporting_spec',
      done: 0,
      total: maxIteration,
    }))
    setJobs(newJobs)

    for (const [i, t] of targets.entries()) {
      const job = newJobs[i]
      try {
        const existing = await lookupSolvedSpotApi(t.fingerprint_type, 0)
        if (existing.spot_id && existing.engine === 'texas') {
          setJobs(js => js.map(j => j.spotId === job.spotId
            ? { ...j, spotId: existing.spot_id!, status: 'done' } : j))
          continue
        }
        await exportSpotSpecApi({
          spot_id: job.spotId,
          fingerprint_type: t.fingerprint_type,
          street: t.street,
          positions: t.positions,
          effective_stack_bb: t.effective_stack_bb,
          pot_bb_at_street_start: t.pot_bb,
          board: t.board,
          bet_size_fractions: fractions,
          n_matching_hands: stats?.total_hands ?? 0,
          overwrite: true,
        })
        await startSolveApi(job.spotId, { maxIteration })
        setJobs(js => js.map(j => j.spotId === job.spotId ? { ...j, status: 'running' } : j))
      } catch (err) {
        setJobs(js => js.map(j => j.spotId === job.spotId ? { ...j, status: 'failed', error: String(err) } : j))
      }
    }
  }

  const stillPending = (s: SolveJob['status']) =>
    s === 'running' || s === 'exporting' || s === 'not_started'

  useEffect(() => {
    if (!jobs.some(j => stillPending(j.status))) return
    const timer = setInterval(async () => {
      for (const job of jobsRef.current) {
        if (!stillPending(job.status)) continue
        try {
          const res = await getSolveStatusApi(job.spotId)
          setJobs(js => js.map(j => j.spotId === job.spotId ? {
            ...j,
            status: res.status,
            done: res.iterations_done ?? j.done,
            total: res.iterations_total ?? j.total,
            exploitability: res.exploitability_pct ?? j.exploitability,
            error: res.error,
          } : j))
        } catch { /* transient */ }
      }
    }, 2500)
    return () => clearInterval(timer)
  }, [jobs])

  // --- Table display ---
  const heroCombo = heroSeat != null && holeCards[heroSeat]
    ? holeCards[heroSeat][0] + holeCards[heroSeat][1] : null

  const seats: BuilderSeat[] = table.seats.map(s => ({
    seatIdx: s.seatIdx,
    position: s.position,
    holeCards: holeCards[s.seatIdx] ?? [null, null],
    stack: s.stack,
    invested: s.invested,
    bet: s.streetBet || null,
    toCall: !s.folded && !s.allIn ? Math.max(0, table.maxStreetBet - s.streetBet) || null : null,
    folded: s.folded,
    isActing: table.toAct === s.seatIdx,
    isHero: heroSeat === s.seatIdx,
    isButton: s.position === 'BTN',
  }))

  const boardCards = useMemo(() => {
    const cards: string[] = []
    for (const b of [table.boards.flop, table.boards.turn, table.boards.river]) {
      if (b) for (let i = 0; i + 1 < b.length; i += 2) cards.push(b.slice(i, i + 2))
    }
    return cards
  }, [table.boards])

  const lastAction = useMemo(() => {
    for (const s of ['river', 'turn', 'flop', 'preflop'] as const) {
      const acts = table.actions[s]
      if (acts.length) return formatAction(acts[acts.length - 1], nPlayers)
    }
    return null
  }, [table.actions, nPlayers])

  const streetPotBB = (st: Street): number | null =>
    derive?.street_progression?.find(p => p.street === st)?.pot_bb ?? null

  const betValue = parseFloat(betInput)
  const betValid = legal?.canRaise && !Number.isNaN(betValue)
    && betValue >= legal.minRaiseTo - 1e-9 && betValue <= legal.maxRaiseTo + 1e-9

  function quickSize(frac: number) {
    if (!legal) return
    const target = Math.min(
      legal.maxRaiseTo,
      Math.max(legal.minRaiseTo, +(table.maxStreetBet + frac * (pot + legal.callAmount)).toFixed(1)),
    )
    setBetInput(String(target))
  }

  function act(ev: TableEvent) {
    setEvents(prev => [...prev, ev])
    setBetInput('')
  }

  const jobStatusBadge = (() => {
    if (jobs.some(j => j.status === 'running' || j.status === 'exporting_spec' || j.status === 'exporting')) return 'Running'
    if (jobs.length && jobs.every(j => j.status === 'done')) return 'Done'
    if (jobs.some(j => j.status === 'failed')) return 'Failed'
    return null
  })()

  const heroPos = heroSeat != null ? positionLabel(nPlayers, heroSeat) : 'Hero'

  return (
    <div className="flex flex-col h-full w-full overflow-hidden bg-ground text-ink">
      <AppChrome
        view={view}
        onView={onView}
        right={
          <>
            <label className="flex items-center gap-2 text-[11px] uppercase tracking-seat font-extrabold text-ink-muted">
              Players
              <select
                value={nPlayers}
                onChange={e => resetHand(Number(e.target.value), stackBB)}
                className="bg-ink border border-divider-strong text-ground px-2.5 py-1.5 text-[11px] font-semibold"
              >
                {[2, 3, 4, 5, 6].map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            <label className="flex items-center gap-2 text-[11px] uppercase tracking-seat font-extrabold text-ink-muted">
              Stacks BB
              <input
                type="number"
                value={stackBB}
                onChange={e => resetHand(nPlayers, Number(e.target.value) || 100)}
                className="w-16 bg-ink border border-divider-strong text-ground px-2 py-1.5 text-[11px] font-semibold tabular-nums"
              />
            </label>
            <Btn onClick={() => setEvents(prev => prev.slice(0, -1))} disabled={events.length === 0}>Undo</Btn>
            <Btn onClick={() => resetHand()}>Reset hand</Btn>
          </>
        }
      />

      <div
        className="flex-1 min-h-0 grid"
        style={{ gridTemplateColumns: 'minmax(0,1fr) 432px' }}
      >
        {/* Left column — table / action bar / log */}
        <div className="min-w-0 border-r-2 border-divider-strong overflow-auto flex flex-col">
          <div className="p-6 flex flex-col gap-5">
            <BuilderTable
              seats={seats}
              tableCaption={`Table · ${nPlayers}-max · ${stackBB} BB deep`}
              board={boardCards}
              boardLabel={boardTexture(derive?.fingerprint_type).toUpperCase()}
              potBB={pot}
              lastAction={lastAction}
              street={table.street}
              reachedStreets={streetsReached(table)}
              onSeatClick={setHeroSeat}
              onSeatCardsClick={seatIdx => setModal({ type: 'hole', seatIdx })}
              onBoardClick={awaiting && awaiting !== 'preflop'
                ? () => setModal({ type: 'board', street: awaiting as Exclude<Street, 'preflop'> })
                : undefined}
            />
          </div>

          {/* Action bar */}
          <div className="border-y-2 border-divider-strong px-6 py-3.5 flex items-center gap-2.5 flex-wrap">
            {legal ? (
              <>
                <span className="font-extrabold text-[11px] tracking-seat uppercase text-ink">
                  {positionLabel(nPlayers, legal.seatIdx)} to act
                </span>
                <Btn variant="fold" onClick={() => act({ kind: 'action', verb: 'f' })}>Fold</Btn>
                <Btn onClick={() => act({ kind: 'action', verb: 'cc' })}>
                  {legal.canCheck ? 'Check' : `Call ${legal.callAmount.toFixed(2)}`}
                </Btn>
                {legal.canRaise && (
                  <>
                    <input
                      type="number"
                      step="0.5"
                      min={legal.minRaiseTo}
                      max={legal.maxRaiseTo}
                      placeholder={`${legal.minRaiseTo.toFixed(1)}+`}
                      value={betInput}
                      onChange={e => setBetInput(e.target.value)}
                      className="w-[92px] bg-ink border border-divider-strong text-ground placeholder:text-ink-dim px-2 py-[7px] text-[12px] tabular-nums"
                    />
                    <Btn
                      variant="accent"
                      className="!text-white"
                      onClick={() => betValid && act({ kind: 'action', verb: 'cbr', amount: betValue })}
                      disabled={!betValid}
                    >
                      {table.maxStreetBet > 0 ? 'Raise to' : 'Bet'}
                    </Btn>
                    <div className="inline-flex">
                      {QUICK_SIZES.map((q, i) => (
                        <button
                          key={q.label}
                          onClick={() => quickSize(q.frac)}
                          className={`font-extrabold text-[11px] tracking-btn uppercase px-[11px] py-[8px] border border-divider-strong text-ink-muted hover:bg-[rgba(243,242,242,.08)] ${i > 0 ? '-ml-px' : ''}`}
                        >
                          {q.label}
                        </button>
                      ))}
                      <button
                        onClick={() => setBetInput(String(legal.maxRaiseTo))}
                        className="font-extrabold text-[11px] tracking-btn uppercase px-[11px] py-[8px] border border-divider-strong text-ink-muted hover:bg-[rgba(243,242,242,.08)] -ml-px"
                      >
                        all-in
                      </button>
                    </div>
                  </>
                )}
              </>
            ) : table.handOver ? (
              <span className="text-[12px] text-ink-muted">Hand over — everyone else folded. Undo or reset to continue building.</span>
            ) : awaiting ? (
              <Btn variant="accent" onClick={() => setModal({ type: 'board', street: awaiting as Exclude<Street, 'preflop'> })}>
                Deal {awaiting}
              </Btn>
            ) : (
              <span className="text-[12px] text-ink-muted">River betting complete — the hand is fully built.</span>
            )}
            <span className="ml-auto text-[11px] text-ink-muted">
              Hero: {heroPos} — click a seat to change
            </span>
          </div>

          {/* Action log */}
          <div className="px-6 py-5 flex flex-col gap-3">
            <SectionLabel className="text-ink-muted">Action log</SectionLabel>
            <div className="grid gap-x-7" style={{ gridTemplateColumns: 'repeat(2, minmax(0,1fr))' }}>
              {(['preflop', 'flop', 'turn', 'river'] as const)
                .filter(st => table.actions[st].length > 0 || st === table.street)
                .map(st => {
                  const acts = table.actions[st]
                  const potHdr = streetPotBB(st)
                  const boardHdr = st !== 'preflop' ? table.boards[st] : null
                  return (
                    <div key={st} className="flex flex-col">
                      <div className="flex items-baseline justify-between border-b border-divider-mid pb-1.5 mb-1">
                        <span className="font-extrabold text-[11px] tracking-seat uppercase text-ink-muted">{st}</span>
                        <span className="text-[11px] text-ink-muted tabular-nums">
                          {boardHdr
                            ? boardHdr.replace(/(..)/g, '$1 ').trim()
                            : potHdr != null ? `${potHdr.toFixed(2)} BB` : ''}
                        </span>
                      </div>
                      {acts.map((a, i) => {
                        const isHero = seatOfAction(a) === heroSeat
                        return (
                          <div
                            key={i}
                            className={`py-1.5 border-b border-divider-light text-[12.5px] ${
                              isHero ? 'font-extrabold text-accent' : 'text-ink'
                            }`}
                          >
                            {formatAction(a, nPlayers)}
                          </div>
                        )
                      })}
                      {st === table.street && legal && (
                        <div className="py-1.5 text-[12.5px] text-ink-muted">
                          {positionLabel(nPlayers, legal.seatIdx)} to act…
                        </div>
                      )}
                    </div>
                  )
                })}
            </div>
          </div>
        </div>

        {/* Right rail */}
        <div className="overflow-auto flex flex-col">
          {/* Situation */}
          <section className="border-b-2 border-divider-strong px-5 py-[18px] flex flex-col gap-3">
            <SectionLabel>Situation</SectionLabel>
            {heroSeat == null && <div className="text-[12px] text-ink-muted">Pick a hero seat to derive the situation.</div>}
            {deriveError && <div className="text-[12px] text-accent-light">{deriveError}</div>}
            {derive && (
              <div className="grid gap-x-3 gap-y-1.5 text-[12.5px]"
                style={{ gridTemplateColumns: '88px minmax(0,1fr)' }}>
                <span className="text-ink-muted">Hero</span>
                <span className="text-ink">
                  {heroPos} · {derive.fingerprint_type.street} · {derive.fingerprint_type.positions} ·{' '}
                  {(derive.fingerprint_type.pot_type ?? '').toUpperCase()}
                </span>
                <span className="text-ink-muted">Facing</span>
                <span className="text-ink">
                  {(derive.fingerprint_type.facing ?? '').replace(/_/g, ' ')}
                  {derive.fingerprint_type.spr_bucket && ` · SPR ${derive.fingerprint_type.spr_bucket}`}
                </span>
                <span className="text-ink-muted">Texture</span>
                <span className="text-ink">{boardTexture(derive.fingerprint_type).replace(/^Board · /, '') || '—'}</span>
                <span className="text-ink-muted">Pot / eff.</span>
                <span className="text-ink font-extrabold tabular-nums">
                  {derive.pot_bb_at_street_start.toFixed(1)} / {derive.effective_stack_bb.toFixed(1)} BB
                </span>
              </div>
            )}
          </section>

          {/* Similar real hands */}
          <section className="border-b-2 border-divider-strong px-5 py-[18px] flex flex-col gap-3">
            <div className="flex items-baseline gap-2">
              <SectionLabel>Similar real hands</SectionLabel>
              <span className="text-[11px] text-ink-muted">888poker</span>
            </div>
            <Segmented
              size="sm"
              options={TIER_CHOICES}
              value={maxTier}
              onChange={setMaxTier}
            />
            {statsLoading && (
              <div className="flex flex-col gap-1">
                {[0, 1, 2].map(i => <div key={i} className="h-4 bg-[#605d5d33]" />)}
              </div>
            )}
            {stats?.tiers && (
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="text-ink-muted border-b-2 border-divider-strong">
                    <th className="text-left font-extrabold uppercase tracking-seat text-[10px] pb-1.5">Match</th>
                    <th className="text-right font-extrabold uppercase tracking-seat text-[10px] pb-1.5">Hands</th>
                    <th className="text-right font-extrabold uppercase tracking-seat text-[10px] pb-1.5">Avg pot</th>
                    <th className="text-right font-extrabold uppercase tracking-seat text-[10px] pb-1.5">Won</th>
                    <th className="text-right font-extrabold uppercase tracking-seat text-[10px] pb-1.5">BB/100</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.tiers.map(t => {
                    const zero = t.total_hands === 0
                    const bb = t.scotty?.bb_per_100 ?? null
                    return (
                      <tr
                        key={t.tier}
                        className={`border-b border-divider-light ${zero ? 'text-ink-dim' : 'text-ink'} ${
                          t.tier === maxTier ? 'bg-accent-tint' : ''
                        }`}
                      >
                        <td className="py-[7px]">{t.label}</td>
                        <td className="py-[7px] text-right tabular-nums">{t.total_hands}</td>
                        <td className="py-[7px] text-right tabular-nums">{t.avg_pot_bb ?? '—'}</td>
                        <td className="py-[7px] text-right tabular-nums">{t.scotty ? `${t.scotty.won_pct}%` : '—'}</td>
                        <td className={`py-[7px] text-right tabular-nums font-extrabold ${
                          bb == null ? '' : bb < 0 ? 'text-accent-light' : 'text-ink'
                        }`}>
                          {bb ?? '—'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
            <HandLookupPanel
              types={derive ? [derive.fingerprint_type] : []}
              venue="888poker"
              fuzzy
              maxTier={maxTier}
              ctaLabel="Find matching real hands"
            />
          </section>

          {/* Solve spot */}
          <section className="px-5 py-[18px] flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <SectionLabel>Solve spot</SectionLabel>
              {jobStatusBadge && (
                <span className="ml-auto"><Badge>{jobStatusBadge}</Badge></span>
              )}
            </div>

            {!derive || derive.solvable_streets.length === 0 ? (
              <div className="text-[12px] text-ink-muted">
                Play the hand to a flop with exactly two players in (hero one of them) and
                the solver unlocks. Preflop-only spots can’t be solved.
              </div>
            ) : (
              <>
                {lookup?.spot_id && (
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge tone={lookup.match_tier === 0 ? 'ink' : 'outline'}>
                      {lookup.match_tier === 0 ? 'Already solved' : `Similar: ${lookup.match_label}`}
                    </Badge>
                    <Btn
                      variant="accent"
                      onClick={() => onOpenSolver({
                        spotId: lookup.spot_id!,
                        heroCombo,
                        heroIsOop: !derive.fingerprint_type.in_position,
                        heroLabel: heroPos,
                        villainLabel: villainFromPositions(derive.fingerprint_type.positions ?? '', heroPos),
                        storedBoard: lookup.board,
                        fingerprintType: derive.fingerprint_type,
                      })}
                    >
                      Open in solver
                    </Btn>
                  </div>
                )}

                <div className="border-t-2 border-divider-strong pt-3 flex flex-col gap-3">
                  <Segmented
                    full
                    options={[
                      { value: 'final' as const, label: 'Final state only' },
                      { value: 'path' as const, label: 'Every decision' },
                    ]}
                    value={solveMode}
                    onChange={setSolveMode}
                  />

                  <div className="flex flex-col gap-1.5">
                    <SectionLabel className="text-ink-muted">Bet sizes in the tree</SectionLabel>
                    <div className="flex flex-wrap gap-1.5">
                      {BET_FRACTION_CHOICES.map(f => {
                        const on = fractions.includes(f)
                        return (
                          <button
                            key={f}
                            onClick={() => setFractions(prev =>
                              prev.includes(f) ? prev.filter(x => x !== f) : [...prev, f].sort((a, b) => a - b))}
                            className={`font-extrabold text-[10px] tracking-btn uppercase px-2 py-1 border ${
                              on ? 'bg-ink text-ground border-ink'
                                 : 'border-divider-strong text-ink-muted hover:bg-[rgba(243,242,242,.08)]'
                            }`}
                          >
                            {f}×
                          </button>
                        )
                      })}
                    </div>
                  </div>

                  <label className="flex items-center gap-2 text-[11px] uppercase tracking-seat font-extrabold text-ink-muted">
                    Iterations
                    <input
                      type="number"
                      step={50}
                      value={maxIteration}
                      onChange={e => setMaxIteration(Math.max(10, Number(e.target.value) || 200))}
                      className="w-[76px] bg-ink border border-divider-strong text-ground px-2 py-1.5 text-[11px] tabular-nums"
                    />
                    <span className="text-ink-dim normal-case tracking-normal font-normal">Full 3-street solve — minutes</span>
                  </label>

                  <Btn
                    variant="accent"
                    className="self-start"
                    onClick={launchSolves}
                    disabled={jobs.some(j => j.status === 'running' || j.status === 'exporting_spec' || j.status === 'exporting')}
                  >
                    Solve now
                  </Btn>
                </div>

                {[...jobs]
                  .sort((a, b) => (STREET_DISPLAY_ORDER[a.street] ?? 9) - (STREET_DISPLAY_ORDER[b.street] ?? 9))
                  .map(job => {
                    const villainPos = villainFromPositions(job.positions, heroPos)
                    const pct = job.total ? Math.min(100, (job.done / job.total) * 100) : 0
                    return (
                      <div key={job.spotId} className="border-t-2 border-divider-strong pt-3 flex flex-col gap-2">
                        <div className="flex items-center justify-between text-[12px]">
                          <span className="text-ink capitalize">
                            {job.street} · {heroPos} (hero, {job.heroIsOop ? 'OOP' : 'IP'}) vs {villainPos}
                          </span>
                          <span className="text-ink-muted tabular-nums">
                            {job.done} / {job.total}
                            {job.exploitability != null && ` · expl. ${job.exploitability.toFixed(2)}%`}
                          </span>
                        </div>
                        <div className="h-2 bg-[rgba(243,242,242,.18)]">
                          <div className="h-full bg-accent" style={{ width: `${pct}%` }} />
                        </div>
                        {job.error && <div className="text-[11px] text-accent-light whitespace-pre-wrap">{job.error}</div>}
                        {job.status === 'done' && (
                          <Btn
                            variant="accent"
                            onClick={() => onOpenSolver({
                              spotId: job.spotId,
                              heroCombo,
                              heroIsOop: job.heroIsOop,
                              heroLabel: heroPos,
                              villainLabel: villainPos,
                              fingerprintType: job.fingerprintType,
                            })}
                          >
                            Open in solver
                          </Btn>
                        )}
                      </div>
                    )
                  })}
              </>
            )}
          </section>
        </div>
      </div>

      {/* Modals */}
      {modal?.type === 'hole' && (
        <CardPickerModal
          title={`${positionLabel(nPlayers, modal.seatIdx)} — hole cards`}
          count={2}
          initial={holeCards[modal.seatIdx] ?? []}
          disabledCards={usedCards.filter(c => !(holeCards[modal.seatIdx] ?? []).includes(c))}
          onConfirm={cards => {
            if (cards.length === 2 && Object.keys(holeCards).length === 0) setHeroSeat(modal.seatIdx)
            setHoleCards(prev => {
              const next = { ...prev }
              if (cards.length === 2) next[modal.seatIdx] = [cards[0], cards[1]]
              else delete next[modal.seatIdx]
              return next
            })
            setModal(null)
          }}
          onCancel={() => setModal(null)}
        />
      )}
      {modal?.type === 'board' && (
        <CardPickerModal
          title={`Deal the ${modal.street}`}
          count={modal.street === 'flop' ? 3 : 1}
          disabledCards={usedCards}
          onConfirm={cards => {
            setEvents(prev => {
              const replayed = buildTable({ nPlayers, stackBB }, prev)
              if (replayed.awaitingBoard !== modal.street) return prev
              return [...prev, { kind: 'board', cards: cards.join('') }]
            })
            setModal(null)
          }}
          onCancel={() => setModal(null)}
        />
      )}
    </div>
  )
}
