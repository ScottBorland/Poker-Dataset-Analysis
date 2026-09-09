import { useEffect, useMemo, useState } from 'react'
import { PokerTable, SeatDisplay } from '../components/PokerTable'
import { ExactCardPicker } from '../components/ExactCardPicker'
import { HandGridPicker } from '../components/HandGridPicker'
import { SpotSelector } from '../components/SpotSelector'
import { StrategyPanel } from '../components/StrategyPanel'
import { RangeBreakdownTable } from '../components/RangeBreakdownTable'
import { FingerprintDistributionChart } from '../components/FingerprintDistributionChart'
import { HandLookupPanel } from '../components/HandLookupPanel'
import {
  getSpotDetailApi, getSpotNodeApi, getFingerprintDistributionApi,
} from '../utils/api'
import {
  SpotDetail, SpotActionOption, NodeDetail,
  FingerprintKey, FingerprintTypeCount,
} from '../types'
import { fingerprintKeyId } from '../utils/fingerprintKey'

type Mode = 'solved' | 'replay'

export default function PokerTablePage() {
  const [mode, setMode] = useState<Mode>('solved')

  return (
    <div className="flex flex-col h-full w-full overflow-hidden bg-gray-50 p-4 gap-3">
      <div className="flex items-center gap-2">
        <h1 className="text-lg font-semibold text-gray-900">Poker Table</h1>
        <div className="flex gap-1 ml-4">
          {(['solved', 'replay'] as const).map(m => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`px-3 py-1 text-sm rounded-md border transition-colors ${
                mode === m
                  ? 'bg-indigo-600 text-white border-indigo-600'
                  : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
              }`}
            >
              {m === 'solved' ? 'Solved Spot' : 'Replay Hand'}
            </button>
          ))}
        </div>
      </div>
      <div className="flex-1 min-h-0 overflow-auto">
        {mode === 'solved' ? <SolvedSpotMode /> : <ReplayMode />}
      </div>
    </div>
  )
}

function SolvedSpotMode() {
  const [spotId, setSpotId] = useState<string | null>(null)
  const [spec, setSpec] = useState<SpotDetail | null>(null)
  const [specError, setSpecError] = useState<string | null>(null)
  const [heroSeat, setHeroSeat] = useState<0 | 1>(0)
  const [heroHand, setHeroHand] = useState<[string | null, string | null]>([null, null])
  const [villainHand, setVillainHand] = useState<[string | null, string | null]>([null, null])
  const [path, setPath] = useState<number[]>([])
  const [terminalBanner, setTerminalBanner] = useState<string | null>(null)
  const [nodeData, setNodeData] = useState<NodeDetail | null>(null)
  const [nodeError, setNodeError] = useState<string | null>(null)
  const [nodeLoading, setNodeLoading] = useState(false)

  useEffect(() => {
    if (!spotId) return
    setSpec(null)
    setSpecError(null)
    setPath([])
    setTerminalBanner(null)
    setVillainHand([null, null])
    getSpotDetailApi(spotId).then(setSpec).catch(err => setSpecError(String(err)))
  }, [spotId])

  const pathKey = path.join(',')
  const heroReady = Boolean(heroHand[0] && heroHand[1])

  // Hand-agnostic: fetches the whole node's breakdown regardless of which
  // exact hands are selected, so hero and villain hand lookups are both
  // done client-side against the same response (see selectedGroup below).
  useEffect(() => {
    if (!spotId || terminalBanner) return
    setNodeLoading(true)
    setNodeError(null)
    getSpotNodeApi(spotId, { action_path: path })
      .then(setNodeData)
      .catch(err => setNodeError(String(err)))
      .finally(() => setNodeLoading(false))
    // path is represented by pathKey below; re-run whenever it changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spotId, pathKey, terminalBanner])

  function handlePick(option: SpotActionOption) {
    if (option.terminal) {
      setTerminalBanner(
        `${option.label} → ${
          option.terminal_type === 'fold'
            ? 'hand ends, no showdown'
            : 'reaches showdown (villain’s exact hand is unknown)'
        }`
      )
    } else if (option.next_path) {
      setVillainHand([null, null])
      setPath(option.next_path)
    }
  }

  function reset() {
    setPath([])
    setTerminalBanner(null)
    setVillainHand([null, null])
  }

  const boardCards = useMemo(() => {
    if (!spec) return []
    return spec.summary.board.match(/.{1,2}/g) ?? []
  }, [spec])

  const isHeroTurn = Boolean(nodeData) && nodeData!.acting_player === heroSeat
  const activeHand = isHeroTurn ? heroHand : villainHand

  const selectedGroup = useMemo(() => {
    if (!nodeData || !activeHand[0] || !activeHand[1]) return null
    const combo1 = activeHand[0] + activeHand[1]
    const combo2 = activeHand[1] + activeHand[0]
    return nodeData.canonical_groups.find(g => g.members.includes(combo1) || g.members.includes(combo2)) ?? null
  }, [nodeData, activeHand])

  const displayFrequencies = selectedGroup ? selectedGroup.frequencies : nodeData?.aggregate ?? {}
  const activeHandReady = Boolean(activeHand[0] && activeHand[1])

  const description = useMemo(() => {
    if (!nodeData) return ''
    const who = isHeroTurn ? "Hero's" : "Villain's"
    if (selectedGroup) {
      const n = selectedGroup.members.length
      return `${who} exact-hand strategy (pooled over ${n} strategically-identical combo${n === 1 ? '' : 's'})`
    }
    if (activeHandReady) {
      return `${activeHand[0]}${activeHand[1]} is outside this seat's assumed range for this spot ` +
        `(dashed cells in the grid below) — showing the range-wide average instead.`
    }
    return isHeroTurn
      ? "Pick hero's exact 2 cards above to see the solved strategy."
      : "Villain's range-wide average — pick an exact villain hand (grid, dropdowns, or a row below) to see that hand specifically."
  }, [nodeData, isHeroTurn, selectedGroup, activeHand, activeHandReady])

  const seats: SeatDisplay[] = useMemo(() => {
    if (!spec) return []
    const villainSeat = heroSeat === 0 ? 1 : 0
    const heroDisplay: SeatDisplay = {
      seatIdx: heroSeat,
      label: `Hero (${heroSeat === 0 ? 'OOP' : 'IP'})`,
      holeCards: [heroHand[0], heroHand[1]],
      stack: spec.summary.effective_stack_bb,
      bet: null,
      folded: false,
      isActing: isHeroTurn && !terminalBanner,
      isHero: true,
    }
    const villainDisplay: SeatDisplay = {
      seatIdx: villainSeat,
      label: `Villain (${villainSeat === 0 ? 'OOP' : 'IP'})`,
      holeCards: [villainHand[0], villainHand[1]],
      stack: spec.summary.effective_stack_bb,
      bet: null,
      folded: false,
      isActing: Boolean(nodeData) && !isHeroTurn && !terminalBanner,
      isHero: false,
    }
    return heroSeat === 0 ? [heroDisplay, villainDisplay] : [villainDisplay, heroDisplay]
  }, [spec, heroHand, villainHand, heroSeat, isHeroTurn, nodeData, terminalBanner])

  const spr = spec ? (spec.summary.effective_stack_bb / spec.summary.pot_bb_at_street_start).toFixed(2) : null
  const heroDisabled = useMemo(
    () => [...boardCards, ...(villainHand.filter(Boolean) as string[])],
    [boardCards, villainHand]
  )
  const villainDisabled = useMemo(
    () => [...boardCards, ...(heroHand.filter(Boolean) as string[])],
    [boardCards, heroHand]
  )
  // heroSeat 0 = OOP, 1 = IP — matches game_def.py's player0=OOP/player1=IP
  // convention, so hero's/villain's assumed range comes from whichever of
  // oop_range_hands/ip_range_hands corresponds to their seat.
  const heroRangeHands = heroSeat === 0 ? spec?.summary.oop_range_hands : spec?.summary.ip_range_hands
  const villainRangeHands = heroSeat === 0 ? spec?.summary.ip_range_hands : spec?.summary.oop_range_hands

  return (
    <div className="flex flex-col gap-3 h-full">
      <SpotSelector selectedSpotId={spotId} onSelect={id => setSpotId(id)} />
      {specError && <div className="text-red-500 text-sm">{specError}</div>}
      {spec && (
        <div className="flex gap-4 flex-1 min-h-0 flex-wrap">
          <div className="flex-1 min-w-[420px] flex flex-col gap-3">
            <PokerTable
              seats={seats}
              board={boardCards}
              pot={spec.summary.pot_bb_at_street_start}
              potLabel={
                `Pot ${spec.summary.pot_bb_at_street_start.toFixed(2)} BB` +
                ` · stacks ${spec.summary.effective_stack_bb.toFixed(1)} BB (SPR ${spr})`
              }
              lastAction={terminalBanner}
            />
            <div className="flex items-center gap-3 text-sm flex-wrap">
              <label className="flex items-center gap-1.5">
                Hero seat:
                <select
                  value={heroSeat}
                  onChange={e => { setHeroSeat(Number(e.target.value) as 0 | 1); reset() }}
                  className="border border-gray-300 rounded px-1.5 py-1 bg-white"
                >
                  <option value={0}>0 — first to act (OOP)</option>
                  <option value={1}>1 — in position (IP)</option>
                </select>
              </label>
              <button
                onClick={reset}
                className="ml-auto px-3 py-1.5 text-xs border border-gray-300 rounded hover:bg-gray-100"
              >
                Reset tree
              </button>
            </div>

            <div className="flex gap-4 flex-wrap">
              <div className="flex flex-col gap-1">
                <HandGridPicker
                  label="Hero's hand"
                  value={heroHand}
                  onChange={hand => { setHeroHand(hand); reset() }}
                  disabledCards={heroDisabled}
                  inRangeHands={heroRangeHands}
                />
                <ExactCardPicker value={heroHand} onChange={hand => { setHeroHand(hand); reset() }} disabledCards={heroDisabled} />
              </div>
              {nodeData && !isHeroTurn && !terminalBanner && (
                <div className="flex flex-col gap-1">
                  <HandGridPicker
                    label="Villain's hand (optional)"
                    value={villainHand}
                    onChange={hand => setVillainHand(hand)}
                    disabledCards={villainDisabled}
                    inRangeHands={villainRangeHands}
                  />
                  <ExactCardPicker value={villainHand} onChange={hand => setVillainHand(hand)} disabledCards={villainDisabled} />
                </div>
              )}
            </div>
          </div>

          <div className="w-full lg:w-[28rem] shrink-0 flex flex-col gap-2 overflow-auto">
            <div className="text-xs text-gray-500">
              Effective stack {spec.summary.effective_stack_bb.toFixed(1)} BB · Pot{' '}
              {spec.summary.pot_bb_at_street_start.toFixed(1)} BB (SPR {spr}) · {spec.summary.n_matching_hands} source hands
            </div>
            {!heroReady && (
              <div className="text-sm text-gray-400">Pick hero's exact 2 cards to see the solved strategy.</div>
            )}
            {heroReady && terminalBanner && (
              <div className="text-sm bg-amber-50 border border-amber-200 text-amber-800 rounded px-3 py-2">
                {terminalBanner}
              </div>
            )}
            {heroReady && !terminalBanner && nodeLoading && <div className="text-sm text-gray-400">Loading node…</div>}
            {heroReady && !terminalBanner && nodeError && <div className="text-sm text-red-500">{nodeError}</div>}
            {heroReady && !terminalBanner && nodeData && (
              <>
                <StrategyPanel
                  options={nodeData.options}
                  frequencies={displayFrequencies}
                  whoseTurn={isHeroTurn ? 'hero' : 'villain'}
                  description={description}
                  onPickAction={handlePick}
                />
                <div className="text-xs text-gray-500 mt-1">
                  {isHeroTurn ? "Hero's" : "Villain's"} full range breakdown at this node:
                </div>
                <RangeBreakdownTable
                  groups={nodeData.canonical_groups}
                  options={nodeData.options}
                  sortByAction={nodeData.options[0]?.action ?? 0}
                  selectedMembers={activeHand[0] && activeHand[1] ? [activeHand[0] + activeHand[1], activeHand[1] + activeHand[0]] : []}
                  onSelectCombo={combo => {
                    const hand: [string, string] = [combo.slice(0, 2), combo.slice(2, 4)]
                    if (isHeroTurn) setHeroHand(hand)
                    else setVillainHand(hand)
                  }}
                />
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

const STREETS = ['preflop', 'flop', 'turn', 'river'] as const

function ReplayMode() {
  const [street, setStreet] = useState<string>('flop')
  const [only888, setOnly888] = useState(true)
  const [types, setTypes] = useState<FingerprintTypeCount[]>([])
  const [distLoading, setDistLoading] = useState(false)
  const [distError, setDistError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Map<string, FingerprintKey>>(new Map())

  useEffect(() => {
    let cancelled = false
    setDistLoading(true)
    setDistError(null)
    getFingerprintDistributionApi(street, 30, only888 ? '888poker' : null)
      .then(res => { if (!cancelled) setTypes(res.types) })
      .catch(err => { if (!cancelled) setDistError(String(err)) })
      .finally(() => { if (!cancelled) setDistLoading(false) })
    return () => { cancelled = true }
  }, [street, only888])

  function toggleSelection(id: string) {
    setSelected(prev => {
      const next = new Map(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        const match = types.find(t => fingerprintKeyId(t.key) === id)
        if (match) next.set(id, match.key)
      }
      return next
    })
  }

  return (
    <div className="flex flex-col gap-3 h-full">
      <div className="flex items-center gap-3">
        <select
          value={street}
          onChange={e => { setStreet(e.target.value); setSelected(new Map()) }}
          className="border border-gray-300 rounded px-2 py-1 text-sm bg-white"
        >
          {STREETS.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <label className="flex items-center gap-1.5 text-sm text-gray-700 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={only888}
            onChange={e => { setOnly888(e.target.checked); setSelected(new Map()) }}
            className="accent-indigo-600"
          />
          888poker only
        </label>
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-3 overflow-auto" style={{ maxHeight: '30%' }}>
        {distLoading && <div className="text-center text-gray-400 py-6 animate-pulse">Loading distribution…</div>}
        {distError && <div className="text-red-500 text-sm py-2">{distError}</div>}
        {!distLoading && !distError && types.length > 0 && (
          <FingerprintDistributionChart types={types} selectedIds={new Set(selected.keys())} onToggle={toggleSelection} />
        )}
      </div>

      <div className="flex-1 min-h-0">
        <HandLookupPanel types={Array.from(selected.values())} venue={only888 ? '888poker' : null} />
      </div>
    </div>
  )
}
