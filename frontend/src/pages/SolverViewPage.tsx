// Solver view (design_handoff_poker_flow, screen 1c). The hero's walked line
// and the solver's recommendation side by side, EV loss called out, a 13x13
// range grid coloured by action, and a combo panel that ties the solve back
// to real 888poker hands. EV / equity come from POST /spots/{id}/line-ev;
// the range grid + action mix come from POST /spots/{id}/tree-node.

import { useEffect, useMemo, useState } from 'react'
import { AppChrome, AppView } from '../components/AppChrome'
import { CardPickerModal } from '../components/CardPickerModal'
import { HandRangeHeatmap } from '../components/HandRangeHeatmap'
import { HandLookupPanel } from '../components/HandLookupPanel'
import { Btn, SectionLabel, PlayingCard, MixBar } from '../components/modernist'
import { prettyLabel } from '../components/TexasStrategyViewer'
import { solverActionColors } from '../utils/categoricalColors'
import { getTexasTreeNodeApi, getLineEvApi, getFingerprintStatsApi } from '../utils/api'
import {
  TreePathStep, TexasNodeResponse, TexasNodeOption, SpotActionOption,
  LineEvResponse, FingerprintStatsResponse, FingerprintKey,
} from '../types'
import { SolverOpenArgs } from './HandBuilderPage'

interface Props {
  args: SolverOpenArgs
  view: AppView
  onView: (v: AppView) => void
  onResolve?: () => void
}

const SUIT_GLYPH: Record<string, string> = { h: '♥', d: '♦', c: '♣', s: '♠' }

function comboTitle(combo: string | null): string {
  if (!combo || combo.length < 4) return '—'
  return `${combo[0]}${combo[2]}${SUIT_GLYPH[combo[1]] ?? ''}${SUIT_GLYPH[combo[3]] ?? ''}`
}

export default function SolverViewPage({ args, view, onView }: Props) {
  const { spotId, heroLabel, villainLabel, heroIsOop, fingerprintType } = args

  const [path, setPath] = useState<TreePathStep[]>([])
  const [terminal, setTerminal] = useState<{ step: TreePathStep; note: string } | null>(null)
  const [selectedCombo, setSelectedCombo] = useState<string | null>(args.heroCombo)
  const [cardPick, setCardPick] = useState<{ afterAction: string; cards: string[] } | null>(null)

  const [node, setNode] = useState<TexasNodeResponse | null>(null)
  const [lineEv, setLineEv] = useState<LineEvResponse | null>(null)
  const [stats, setStats] = useState<FingerprintStatsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [showReplay, setShowReplay] = useState(false)

  const combo = selectedCombo
  const pathKey = JSON.stringify(path)
  const evPath = useMemo(
    () => (terminal ? [...path, terminal.step] : path),
    [pathKey, terminal],
  )

  // tree-node — range grid + action mix at the current (non-terminal) node
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getTexasTreeNodeApi(spotId, path, combo)
      .then(res => { if (!cancelled) setNode(res) })
      .catch(err => { if (!cancelled) setError(String(err)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spotId, pathKey, combo])

  // line-ev — per-decision EV, total loss, combo equity
  useEffect(() => {
    if (!combo) { setLineEv(null); return }
    let cancelled = false
    getLineEvApi(spotId, evPath, combo)
      .then(res => { if (!cancelled) setLineEv(res) })
      .catch(() => { if (!cancelled) setLineEv(null) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spotId, JSON.stringify(evPath), combo])

  useEffect(() => {
    let cancelled = false
    getFingerprintStatsApi([fingerprintType], '888poker', true, 4)
      .then(res => { if (!cancelled) setStats(res) })
      .catch(() => { if (!cancelled) setStats(null) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(fingerprintType)])

  const chanceCount = path.filter(s => s.kind === 'chance').length

  const panelOptions: SpotActionOption[] = useMemo(() => (
    (node?.options ?? []).map(o => ({
      action: o.action,
      label: prettyLabel(o.label),
      next_path: null,
      terminal: o.next === 'terminal',
      terminal_type: o.label === 'FOLD' ? 'fold' as const : 'showdown' as const,
    }))
  ), [node])

  const isHeroTurn = node?.node_type === 'action' && node.acting_role === (heroIsOop ? 'oop' : 'ip')

  const selectedMembers = useMemo(() => {
    if (!combo) return []
    return [combo, combo.slice(2) + combo.slice(0, 2)]
  }, [combo])

  function pickOption(opt: TexasNodeOption) {
    if (opt.next === 'action') {
      setTerminal(null)
      setPath(p => [...p, { kind: 'action', value: opt.label }])
    } else if (opt.next === 'chance') {
      setCardPick({ afterAction: opt.label, cards: opt.chance_cards ?? [] })
    } else if (opt.label === 'FOLD') {
      setTerminal({ step: { kind: 'action', value: 'FOLD' }, note: 'Fold — hand ends.' })
    } else if (chanceCount >= 2) {
      setTerminal({ step: { kind: 'action', value: opt.label }, note: 'Showdown.' })
    } else {
      setTerminal({
        step: { kind: 'action', value: opt.label },
        note: 'Line continues on a later street — beyond the stored solve depth. '
          + 'Re-solve from the later street to inspect it.',
      })
    }
  }

  function back() {
    if (terminal) { setTerminal(null); return }
    setPath(p => p.slice(0, -1))
  }

  // --- solution header breadcrumb ---
  const crumbs = useMemo(() => {
    const out: { label: string; current: boolean }[] = []
    if (lineEv?.board) out.push({ label: lineEv.board.replace(/(..)/g, '$1 ').trim(), current: false })
    evPath.forEach(s => out.push({
      label: s.kind === 'chance' ? s.value : prettyLabel(s.value),
      current: false,
    }))
    if (out.length) out[out.length - 1].current = true
    return out
  }, [JSON.stringify(evPath), lineEv?.board])

  const totalLoss = lineEv?.total_ev_loss ?? 0
  const lossColor = totalLoss < -1e-6 ? 'text-accent-light' : 'text-ink'

  // solver line rows = the best action + its solver frequency per hero decision
  const solverRows = (lineEv?.line ?? []).map(r => {
    if (r.actor === 'villain') {
      return { street: r.street, text: r.chosen_pretty, right: r.solver_freq }
    }
    const best = r.options.find(o => o.label === r.best_label)
    return { street: r.street, text: r.best_pretty ?? r.chosen_pretty, right: best?.solver_freq ?? null }
  })

  // action-mix at the current node
  const mix = lineEv?.current_node
  const mixItems = mix ? (mix.hero_action_mix ?? mix.action_mix) : []
  const mixColors = solverActionColors(mixItems.map(m => m.label))

  const combE = lineEv?.combo

  const realHandsSentence = (() => {
    if (!stats) return null
    const n = stats.total_hands
    const won = stats.scotty?.won_pct
    const bb = stats.scotty?.bb_per_100
    const parts = [`${n} similar hand${n === 1 ? '' : 's'} in the 888poker set`]
    if (stats.avg_pot_bb != null) parts.push(`avg pot ${stats.avg_pot_bb} BB`)
    if (won != null) parts.push(`won ${won}%`)
    if (bb != null) parts.push(`${bb} bb/100`)
    return parts.join(' · ') + '.'
  })()

  return (
    <div className="flex flex-col h-full w-full overflow-hidden bg-ground text-ink">
      <AppChrome view={view} onView={onView} />

      {/* Solution header */}
      <div className="flex items-center gap-3 px-5 py-4 border-b-2 border-divider-strong shrink-0 flex-wrap">
        <span className="font-extrabold text-[13px] tracking-brand uppercase">
          Solution · {heroLabel} vs {villainLabel} · {(fingerprintType.pot_type ?? '').toUpperCase()}
        </span>
        <div className="flex items-center gap-1.5 flex-wrap">
          {crumbs.map((c, i) => (
            <span key={i} className="flex items-center gap-1.5">
              {i > 0 && <span className="text-ink-muted">›</span>}
              {c.current ? (
                <span className="bg-accent text-ground font-extrabold text-[11px] px-1.5 py-[2px]">{c.label}</span>
              ) : (
                <span className="text-ink font-semibold text-[11px]">{c.label}</span>
              )}
            </span>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-4 text-[11px] text-ink-muted">
          {(path.length > 0 || terminal) && <Btn onClick={back}>Back</Btn>}
          {(path.length > 0 || terminal) && (
            <Btn onClick={() => { setPath([]); setTerminal(null) }}>Reset</Btn>
          )}
          <Btn onClick={() => onView('solver')}>All solutions</Btn>
          <Btn onClick={() => onView('builder')}>Re-solve</Btn>
        </div>
      </div>

      <div className="flex-1 min-h-0 flex flex-col overflow-auto">
        {/* Top band — your line | solver line */}
        <div className="grid border-b-2 border-divider-strong" style={{ gridTemplateColumns: '1fr 1fr' }}>
          {/* Your line */}
          <div className="border-r-2 border-divider-strong px-5 py-4 flex flex-col gap-3">
            <div className="flex items-baseline justify-between">
              <SectionLabel>Your line</SectionLabel>
              <span className={`font-extrabold text-[12px] tabular-nums ${lossColor}`}>
                {totalLoss > -1e-6 ? '±0.00' : totalLoss.toFixed(2)} BB total EV
              </span>
            </div>
            {!combo && <div className="text-[12px] text-ink-muted">Set the hero's hole cards to score the line.</div>}
            {(lineEv?.line ?? []).map((r, i) => (
              <div key={i} className="grid items-center border-b border-divider-light pb-[11px]"
                style={{ gridTemplateColumns: '64px minmax(0,1fr) 78px' }}>
                <span className="font-extrabold text-[10px] tracking-label uppercase text-ink-muted">{r.street}</span>
                <span className="text-[13px] font-semibold text-ink">
                  {r.actor === 'villain' ? `${villainLabel}: ` : `${heroLabel}: `}{r.chosen_pretty}
                  {r.approx && <span className="text-ink-dim text-[10px]"> ~approx</span>}
                </span>
                <span className={`text-right font-extrabold text-[12px] tabular-nums ${
                  r.ev_delta == null ? 'text-ink-dim'
                    : r.ev_delta < -1e-6 ? 'text-accent'
                    : 'text-ink'
                }`}>
                  {r.ev_delta == null ? '—'
                    : `${r.ev_delta >= 0 ? '+' : ''}${r.ev_delta.toFixed(2)}`}
                </span>
              </div>
            ))}
            {terminal && <div className="text-[12px] text-ink-muted">{terminal.note}</div>}

            {lineEv?.largest_leak && (
              <div className="bg-surface border-l-[3px] border-accent px-3.5 py-3.5 flex flex-col gap-1.5">
                <div className="font-extrabold text-[10px] tracking-label uppercase text-accent-light">Largest leak</div>
                <div className="text-[12.5px] text-ink">
                  {lineEv.largest_leak.chosen_pretty} on the {lineEv.largest_leak.street} costs{' '}
                  <span className="font-extrabold text-accent">
                    {lineEv.largest_leak.ev_delta.toFixed(2)} BB
                  </span>{' '}
                  vs {lineEv.largest_leak.best_pretty ?? 'the solver line'}
                  {lineEv.largest_leak.solver_best_freq != null &&
                    ` — solver takes your action ${(lineEv.largest_leak.solver_best_freq * 100).toFixed(0)}% here`}.
                  {lineEv.largest_leak.approx && ' (later streets estimated by raw equity.)'}
                </div>
              </div>
            )}
          </div>

          {/* Solver line */}
          <div className="px-5 py-4 flex flex-col gap-3">
            <div className="flex items-baseline justify-between">
              <SectionLabel>Solver line</SectionLabel>
              <span className="text-[11px] text-ink-muted">baseline</span>
            </div>
            {solverRows.map((r, i) => (
              <div key={i} className="grid items-center border-b border-divider-light pb-[11px]"
                style={{ gridTemplateColumns: '64px minmax(0,1fr) 78px' }}>
                <span className="font-extrabold text-[10px] tracking-label uppercase text-ink-muted">{r.street}</span>
                <span className="text-[13px] font-semibold text-ink">{r.text}</span>
                <span className="text-right font-semibold text-[12px] tabular-nums text-ink-muted">
                  {r.right == null ? '—' : `${(r.right * 100).toFixed(0)}%`}
                </span>
              </div>
            ))}

            {node?.node_type === 'action' && !terminal && (
              <div className="flex flex-col gap-1.5">
                <div className="font-extrabold text-[10px] tracking-label uppercase text-ink-muted">
                  {isHeroTurn ? `${heroLabel} (hero) to act` : `${villainLabel} to act`} — walk the line
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {(node.options ?? []).map(o => (
                    <Btn
                      key={o.action}
                      variant={o.label === 'FOLD' ? 'fold' : 'outline'}
                      onClick={() => pickOption(o)}
                    >
                      {prettyLabel(o.label)}
                      {node.hero_frequencies && isHeroTurn &&
                        ` ${(Number(node.hero_frequencies[String(o.action)] ?? 0) * 100).toFixed(0)}%`}
                    </Btn>
                  ))}
                </div>
              </div>
            )}

            {mixItems.length > 0 && (
              <div className="bg-surface px-3.5 py-3.5 flex flex-col gap-2">
                <div className="font-extrabold text-[10px] tracking-label uppercase text-ink-muted">
                  Action mix at this node{mix?.actor === 'hero' ? ` · ${comboTitle(combo)}` : ` · ${villainLabel} range`}
                </div>
                <MixBar
                  segments={mixItems.map((m, i) => ({ key: m.label, pct: m.freq, color: mixColors[i] }))}
                />
                <div className="flex gap-3 flex-wrap text-[10.5px] font-semibold text-ink-muted">
                  {mixItems.map((m, i) => (
                    <span key={m.label} className="flex items-center gap-1.5">
                      <span className="w-2.5 h-2.5 inline-block" style={{ backgroundColor: mixColors[i] }} />
                      {m.pretty} {(m.freq * 100).toFixed(0)}%
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Bottom band — hero range | combo panel */}
        <div className="grid flex-1 min-h-0" style={{ gridTemplateColumns: 'minmax(0,1fr) 400px' }}>
          <div className="border-r-2 border-divider-strong px-5 py-4 flex flex-col gap-3 overflow-auto">
            <div className="flex items-baseline gap-2">
              <SectionLabel>Hero range · 13×13</SectionLabel>
              <span className="text-[11px] text-ink-muted">
                Cell fill = action frequency{combo && ` · ${comboTitle(combo)} highlighted`}
              </span>
            </div>
            {error && <div className="text-[12px] text-accent-light">{error}</div>}
            {loading && !node && (
              <div className="flex flex-col gap-[2px]">
                {Array.from({ length: 8 }).map((_, i) => <div key={i} className="h-6 bg-[#605d5d33]" />)}
              </div>
            )}
            {node?.node_type === 'action' && (
              <HandRangeHeatmap
                groups={node.canonical_groups ?? []}
                options={panelOptions}
                selectedMembers={selectedMembers}
                onSelectCombo={setSelectedCombo}
              />
            )}
            {node?.node_type === 'chance' && (
              <div className="text-[12px] text-ink-muted">Pick the next card to continue the line.</div>
            )}
          </div>

          {/* Combo panel */}
          <div className="px-5 py-4 flex flex-col gap-3 overflow-auto">
            <SectionLabel>{comboTitle(combo)} — your combo</SectionLabel>
            {!combo ? (
              <div className="text-[12px] text-ink-muted">Click a cell in the range grid to inspect a combo.</div>
            ) : (
              <>
                <div className="flex items-start gap-3">
                  <div className="flex gap-[3px]">
                    <PlayingCard card={combo.slice(0, 2)} w={44} h={62} />
                    <PlayingCard card={combo.slice(2, 4)} w={44} h={62} />
                  </div>
                  <div className="flex flex-col gap-1">
                    <span className="text-[11px] text-ink-muted">{combE?.hand_class ?? '—'}</span>
                    <span className="font-extrabold text-[13px] text-ink">
                      {combE ? `${(combE.equity_vs_range * 100).toFixed(1)}% equity vs ${villainLabel} range` : '—'}
                    </span>
                  </div>
                </div>

                {(combE?.actions ?? []).map(a => {
                  const cols = solverActionColors((combE?.actions ?? []).map(x => x.label))
                  const idx = (combE?.actions ?? []).indexOf(a)
                  return (
                    <div key={a.label} className="flex flex-col gap-1">
                      <div className="flex items-baseline justify-between text-[12px]">
                        <span className="text-ink">{a.pretty}</span>
                        <span className="text-ink-muted tabular-nums">
                          {a.solver_freq != null ? `${(a.solver_freq * 100).toFixed(0)}%` : '—'} · EV {a.ev >= 0 ? '+' : ''}{a.ev.toFixed(2)}
                        </span>
                      </div>
                      <div className="h-2.5 bg-[rgba(243,242,242,.14)]">
                        <div className="h-full" style={{
                          width: `${(a.solver_freq ?? 0) * 100}%`,
                          backgroundColor: cols[idx],
                        }} />
                      </div>
                    </div>
                  )
                })}

                <div className="border-t-2 border-divider-strong pt-3 flex flex-col gap-2">
                  <SectionLabel className="text-ink-muted">Real hands in this spot</SectionLabel>
                  <div className="text-[12.5px] text-ink">{realHandsSentence ?? 'Loading population stats…'}</div>
                  <Btn variant="accent" className="w-full" onClick={() => setShowReplay(v => !v)}>
                    {showReplay ? 'Hide those hands' : 'Replay those hands'}
                  </Btn>
                  {showReplay && (
                    <HandLookupPanel
                      types={[fingerprintType]}
                      venue="888poker"
                      fuzzy
                      maxTier={4}
                      ctaLabel="Load matching hands"
                    />
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {cardPick && (
        <CardPickerModal
          title={`Pick the ${chanceCount === 0 ? 'turn' : 'river'} card`}
          count={1}
          disabledCards={[
            ...(lineEv?.board ? lineEv.board.match(/../g) ?? [] : []),
            ...(combo ? [combo.slice(0, 2), combo.slice(2, 4)] : []),
          ]}
          onConfirm={cards => {
            if (cards.length === 1) {
              setTerminal(null)
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
