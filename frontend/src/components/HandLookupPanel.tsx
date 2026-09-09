// Given one or more fingerprint keys, loads matching real hands from the DB
// and replays whichever one the user clicks. Modernist dark treatment.

import { useEffect, useState } from 'react'
import { PokerTable, SeatDisplay } from './PokerTable'
import { HandsTable } from './HandsTable'
import { Btn } from './modernist'
import { getFingerprintHandsApi, getHandReplayApi } from '../utils/api'
import { FingerprintKey, FingerprintHandRow, ReplayResponse } from '../types'

const HANDS_PAGE_SIZE = 100

interface Props {
  types: FingerprintKey[]
  venue?: string | null
  onTotalChange?: (total: number) => void
  fuzzy?: boolean
  maxTier?: number
  /** Label for the primary button (defaults to the handoff wording). */
  ctaLabel?: string
}

export function HandLookupPanel({
  types, venue = null, onTotalChange, fuzzy = false, maxTier = 4,
  ctaLabel = 'Find matching real hands',
}: Props) {
  const [hands, setHands] = useState<FingerprintHandRow[]>([])
  const [handsTotal, setHandsTotal] = useState(0)
  const [handsOffset, setHandsOffset] = useState(0)
  const [handsLoading, setHandsLoading] = useState(false)
  const [handsError, setHandsError] = useState<string | null>(null)
  const [handsLoaded, setHandsLoaded] = useState(false)
  const [tierLabels, setTierLabels] = useState<string[] | null>(null)

  const [replay, setReplay] = useState<ReplayResponse | null>(null)
  const [replayLoading, setReplayLoading] = useState(false)
  const [replayError, setReplayError] = useState<string | null>(null)
  const [stepIdx, setStepIdx] = useState(0)

  const typesKey = JSON.stringify(types)
  useEffect(() => {
    setHands([])
    setHandsTotal(0)
    setHandsOffset(0)
    setHandsLoaded(false)
    setHandsError(null)
    setReplay(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [typesKey, venue, fuzzy, maxTier])

  async function loadHands(offset: number) {
    if (types.length === 0) return
    setHandsLoading(true)
    setHandsError(null)
    try {
      const res = await getFingerprintHandsApi(types, HANDS_PAGE_SIZE, offset, venue, fuzzy, maxTier)
      setHands(res.hands)
      setHandsTotal(res.total)
      setHandsOffset(res.offset)
      setHandsLoaded(true)
      setTierLabels(res.tier_labels ?? null)
      onTotalChange?.(res.total)
    } catch (err) {
      setHandsError(String(err))
    } finally {
      setHandsLoading(false)
    }
  }

  async function openHand(row: FingerprintHandRow) {
    setReplayLoading(true)
    setReplayError(null)
    setReplay(null)
    try {
      const res = await getHandReplayApi(row.hand_id, row.file, row.venue)
      setReplay(res)
      setStepIdx(0)
    } catch (err) {
      setReplayError(String(err))
    } finally {
      setReplayLoading(false)
    }
  }

  const step = replay?.steps[stepIdx] ?? null

  const seats: SeatDisplay[] = (() => {
    if (!replay || !step) return []
    return replay.players.map((name, i) => {
      const seatIdx = i + 1
      const key = String(seatIdx)
      const cards = step.hole_cards[key] ?? step.shown_cards[key] ?? []
      return {
        seatIdx,
        label: `${name} (${replay.positions[key] ?? seatIdx})`,
        holeCards: cards.length === 2 ? cards : [null, null],
        stack: step.stacks[i] ?? null,
        bet: step.street_bets[i] ?? null,
        folded: step.folded.includes(seatIdx),
        isActing: step.current_actor === seatIdx,
        isHero: name === 'ScottyWotty',
        isButton: seatIdx === replay.players.length,
      }
    })
  })()

  return (
    <div className="flex flex-col gap-3">
      <Btn
        variant="accent"
        onClick={() => loadHands(0)}
        disabled={types.length === 0 || handsLoading}
        className="w-full"
      >
        {handsLoading ? 'Loading…' : ctaLabel}
      </Btn>

      <div className="flex gap-4 flex-1 min-h-0 flex-wrap">
        <div className="w-full min-h-0">
          {handsError && <div className="text-accent-light text-xs">{handsError}</div>}
          {!handsError && handsLoaded && (
            <div className="h-full flex flex-col gap-1">
              <div className="text-[11px] text-ink-muted uppercase tracking-seat font-extrabold">
                Select a hand row to replay it on the table
              </div>
              <div className="flex-1 min-h-0" style={{ maxHeight: 280 }}>
                <HandsTable
                  hands={hands} total={handsTotal} limit={HANDS_PAGE_SIZE} offset={handsOffset}
                  onPageChange={loadHands} onRowClick={openHand} tierLabels={tierLabels}
                />
              </div>
            </div>
          )}
        </div>

        {(replay || replayLoading || replayError) && (
          <div className="w-full min-h-0 flex flex-col gap-2">
            {replayLoading && <div className="text-xs text-ink-muted">Loading hand…</div>}
            {replayError && <div className="text-xs text-accent-light">{replayError}</div>}
            {replay && step && (
              <>
                <PokerTable
                  seats={seats}
                  board={step.board}
                  pot={step.total_pot}
                  potLabel={`Pot $${step.total_pot.toFixed(2)}`}
                  lastAction={step.action_log[step.action_log.length - 1] ?? null}
                />
                <div className="flex items-center gap-2">
                  <Btn onClick={() => setStepIdx(0)} disabled={stepIdx === 0}>Reset</Btn>
                  <Btn onClick={() => setStepIdx(i => Math.max(0, i - 1))} disabled={stepIdx === 0}>Prev</Btn>
                  <Btn
                    onClick={() => setStepIdx(i => Math.min(replay.steps.length - 1, i + 1))}
                    disabled={stepIdx >= replay.steps.length - 1}
                  >
                    Next
                  </Btn>
                  <span className="text-[11px] text-ink-muted tabular-nums">
                    Step {step.display_step + 1} / {replay.steps.length}
                  </span>
                </div>
                <div className="flex-1 min-h-0 overflow-auto border border-divider-mid p-2 text-[11px] text-ink-muted bg-surface">
                  {step.action_log.map((line, i) => <div key={i}>{line}</div>)}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
