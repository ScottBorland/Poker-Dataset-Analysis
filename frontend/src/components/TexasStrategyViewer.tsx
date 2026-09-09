// Walks a TexasSolver-solved strategy tree via /spots/{id}/tree-node.
// Same StrategyPanel + RangeBreakdownTable rendering as the legacy MCCFR
// viewer, but the path is a list of labeled actions and chance cards: when
// a line crosses a street boundary (bet-call or check-check), the user
// picks the turn/river card via CardPickerModal before continuing.
//
// Stored dumps are depth-limited (dump_rounds, default 2 betting rounds) —
// walking past the stored depth shows a "beyond stored depth" note rather
// than pretending the line is terminal.

import { useEffect, useMemo, useState } from 'react'
import { StrategyPanel } from './StrategyPanel'
import { RangeBreakdownTable } from './RangeBreakdownTable'
import { HandRangeHeatmap } from './HandRangeHeatmap'
import { HandCategoryChart } from './HandCategoryChart'
import { CardPickerModal } from './CardPickerModal'
import { getTexasTreeNodeApi } from '../utils/api'
import { TreePathStep, TexasNodeResponse, TexasNodeOption, SpotActionOption } from '../types'

export function prettyLabel(label: string): string {
  const m = label.match(/^(BET|RAISE)\s+([\d.]+)$/)
  if (m) {
    const amt = parseFloat(m[2])
    return `${m[1] === 'BET' ? 'Bet' : 'Raise to'} ${amt % 1 === 0 ? amt : amt.toFixed(2)} BB`
  }
  return label.charAt(0) + label.slice(1).toLowerCase()
}

interface Props {
  spotId: string
  heroCards: [string | null, string | null]
  heroIsOop: boolean
  /** Cards already used (board + both players' hole cards) — disabled in
   *  the runout card picker. */
  usedCards?: string[]
  /** Position names for the two seats (e.g. 'BB', 'CO') — used in the
   *  whose-turn banner and descriptions. */
  heroLabel?: string
  villainLabel?: string
  /** Fires whenever the walked line changes (including reset to root), and
   *  with `terminal` set when a line-ending action (fold / final call) is
   *  picked — lets the Hand Builder mirror the line on the table visual. */
  onLineChange?: (path: TreePathStep[], terminal?: string) => void
}

export function TexasStrategyViewer({
  spotId, heroCards, heroIsOop, usedCards = [], heroLabel = 'Hero', villainLabel = 'Villain',
  onLineChange,
}: Props) {
  const [path, setPath] = useState<TreePathStep[]>([])
  const [node, setNode] = useState<TexasNodeResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [terminalNote, setTerminalNote] = useState<string | null>(null)
  const [cardPick, setCardPick] = useState<{ afterAction: string; cards: string[] } | null>(null)
  const [rangeView, setRangeView] = useState<'grid' | 'table'>('grid')

  const heroCombo = heroCards[0] && heroCards[1] ? heroCards[0] + heroCards[1] : null
  const pathKey = JSON.stringify(path)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getTexasTreeNodeApi(spotId, path, heroCombo)
      .then(res => { if (!cancelled) setNode(res) })
      .catch(err => { if (!cancelled) setError(String(err)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spotId, pathKey, heroCombo])

  // Street tracked from how many chance cards have been dealt in the path.
  const chanceCount = path.filter(s => s.kind === 'chance').length

  // Mirror the walked line to the parent (table visual) on every change.
  useEffect(() => {
    onLineChange?.(path)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathKey])

  function pickOption(opt: TexasNodeOption) {
    if (opt.next === 'action') {
      setPath(p => [...p, { kind: 'action', value: opt.label }])
    } else if (opt.next === 'chance') {
      setCardPick({ afterAction: opt.label, cards: opt.chance_cards ?? [] })
    } else if (opt.label === 'FOLD') {
      setTerminalNote('Fold — hand ends.')
      onLineChange?.(path, opt.label)
    } else if (chanceCount >= 2) {
      setTerminalNote('Showdown.')
      onLineChange?.(path, opt.label)
    } else {
      setTerminalNote(
        'Line continues on a later street, but the stored solution only keeps '
        + 'the first two betting rounds (dump depth). Re-solve from the later '
        + 'street in the Hand Builder to inspect it.'
      )
      onLineChange?.(path, opt.label)
    }
  }

  const isHeroTurn = node?.node_type === 'action' && node.acting_role === (heroIsOop ? 'oop' : 'ip')

  // Adapt to StrategyPanel's SpotActionOption shape.
  const panelOptions: SpotActionOption[] = useMemo(() => (
    (node?.options ?? []).map(o => ({
      action: o.action,
      label: prettyLabel(o.label),
      next_path: null,
      terminal: o.next === 'terminal',
      terminal_type: o.label === 'FOLD' ? 'fold' as const : 'showdown' as const,
    }))
  ), [node])

  const heroGroup = useMemo(() => {
    if (!node?.canonical_groups || !heroCombo) return null
    const alt = heroCombo.slice(2) + heroCombo.slice(0, 2)
    return node.canonical_groups.find(g => g.members.includes(heroCombo) || g.members.includes(alt)) ?? null
  }, [node, heroCombo])

  const displayFrequencies = (isHeroTurn && node?.hero_frequencies)
    ? node.hero_frequencies
    : node?.aggregate ?? {}

  const description = !node ? '' : isHeroTurn
    ? node.hero_frequencies
      ? `${heroLabel}'s exact strategy with ${heroCards[0]}${heroCards[1]}`
      : heroCombo
      ? `${heroCombo} is outside the assumed range here — showing ${heroLabel}'s range-wide average.`
      : `${heroLabel}'s range-wide average (set hero's cards to see the exact hand).`
    : `${villainLabel}'s range-wide average at this node.`

  const breadcrumb = path.map(s =>
    s.kind === 'chance' ? `[${s.value}]` : prettyLabel(s.value)
  ).join(' → ')

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2 text-xs text-gray-500 flex-wrap">
        <span className="font-medium">{breadcrumb || 'Root'}</span>
        {(path.length > 0 || terminalNote) && (
          <>
            <button
              onClick={() => {
                // If a terminal action is displayed, "Back" first clears it
                // (the path itself hasn't advanced); otherwise pop a step.
                const next = terminalNote ? path : path.slice(0, -1)
                setPath(next)
                setTerminalNote(null)
                onLineChange?.(next)
              }}
              disabled={path.length === 0 && !terminalNote}
              className="ml-auto px-2 py-0.5 border border-gray-300 rounded hover:bg-gray-100 disabled:opacity-40"
            >
              Back
            </button>
            <button
              onClick={() => { setPath([]); setTerminalNote(null); onLineChange?.([]) }}
              className="px-2 py-0.5 border border-gray-300 rounded hover:bg-gray-100"
            >
              Reset tree
            </button>
          </>
        )}
      </div>

      {terminalNote && (
        <div className="text-sm bg-amber-50 border border-amber-200 text-amber-800 rounded px-3 py-2">
          {terminalNote}
        </div>
      )}
      {!terminalNote && loading && <div className="text-xs text-gray-400 animate-pulse">Loading node…</div>}
      {!terminalNote && error && <div className="text-xs text-red-500">{error}</div>}
      {!terminalNote && !loading && node?.node_type === 'action' && (
        <>
          {/* Whose decision this node shows — mirrors the table's gold
              acting highlight for the hero, slate for the villain. */}
          <div className="flex items-center gap-1.5">
            <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold ${
              isHeroTurn ? 'bg-amber-400 text-slate-900' : 'bg-slate-700 text-slate-100'
            }`}>
              <span className={`w-2 h-2 rounded-full ${isHeroTurn ? 'bg-slate-900' : 'bg-slate-300'}`} />
              {isHeroTurn ? `${heroLabel} (hero) to act` : `${villainLabel} (villain) to act`}
            </span>
            <span className="text-[11px] text-gray-400">
              {node.acting_role === 'oop' ? 'out of position' : 'in position'}
            </span>
          </div>
          <StrategyPanel
            options={panelOptions}
            frequencies={displayFrequencies}
            whoseTurn={isHeroTurn ? 'hero' : 'villain'}
            description={description}
            onPickAction={opt => {
              const raw = node.options?.[opt.action]
              if (raw) pickOption(raw)
            }}
          />
          {(() => {
            const selectedMembers = heroGroup && heroCombo
              ? [heroCombo, heroCombo.slice(2) + heroCombo.slice(0, 2)]
              : []
            return (
              <>
                <div className="flex items-center gap-1 text-xs">
                  <button
                    onClick={() => setRangeView('grid')}
                    className={`px-2 py-0.5 border rounded-l ${rangeView === 'grid' ? 'bg-gray-800 text-white border-gray-800' : 'border-gray-300 hover:bg-gray-100'}`}
                  >
                    Grid
                  </button>
                  <button
                    onClick={() => setRangeView('table')}
                    className={`px-2 py-0.5 border rounded-r -ml-px ${rangeView === 'table' ? 'bg-gray-800 text-white border-gray-800' : 'border-gray-300 hover:bg-gray-100'}`}
                  >
                    Table
                  </button>
                </div>
                {rangeView === 'grid' ? (
                  <HandRangeHeatmap
                    groups={node.canonical_groups ?? []}
                    options={panelOptions}
                    selectedMembers={selectedMembers}
                  />
                ) : (
                  <RangeBreakdownTable
                    groups={node.canonical_groups ?? []}
                    options={panelOptions}
                    sortByAction={panelOptions[0]?.action ?? 0}
                    selectedMembers={selectedMembers}
                  />
                )}
              </>
            )
          })()}
          <HandCategoryChart categories={node.category_groups ?? []} options={panelOptions} />
        </>
      )}

      {cardPick && (
        <CardPickerModal
          title={`Pick the ${chanceCount === 0 ? 'turn' : 'river'} card`}
          count={1}
          disabledCards={usedCards}
          onConfirm={cards => {
            if (cards.length === 1) {
              setPath(p => [
                ...p,
                { kind: 'action', value: cardPick.afterAction },
                { kind: 'chance', value: cards[0] },
              ])
            }
            setCardPick(null)
          }}
          onCancel={() => setCardPick(null)}
        />
      )}
    </div>
  )
}
