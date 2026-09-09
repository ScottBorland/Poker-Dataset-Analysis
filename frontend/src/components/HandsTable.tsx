import { FingerprintHandRow } from '../types'

function fmtBB(net_won: number | null, big_blind: number | null): string {
  if (net_won == null || big_blind == null || big_blind === 0) return '—'
  const bb = net_won / big_blind
  return `${bb >= 0 ? '+' : ''}${bb.toFixed(2)}`
}

interface Props {
  hands: FingerprintHandRow[]
  total: number
  limit: number
  offset: number
  onPageChange: (offset: number) => void
  onRowClick?: (row: FingerprintHandRow) => void
  tierLabels?: string[] | null
}

const COLUMNS = [
  'hand_id', 'player_id', 'position', 'street', 'pot_type', 'facing',
  'spr_bucket', 'board', 'stack', 'invested', 'net_won', 'venue', 'date',
]

export function HandsTable({ hands, total, limit, offset, onPageChange, onRowClick, tierLabels }: Props) {
  if (hands.length === 0) {
    return <div className="px-3 py-6 text-center text-ink-dim text-xs uppercase tracking-seat font-extrabold">No hands loaded</div>
  }

  const from = offset + 1
  const to = offset + hands.length

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-auto border border-divider-mid">
        <table className="min-w-full text-[11px]">
          <thead className="sticky top-0 bg-surface border-b-2 border-divider-strong">
            <tr className="text-ink-muted">
              {tierLabels && <th className="px-2 py-1.5 text-left font-extrabold uppercase tracking-seat text-[10px]">match</th>}
              {COLUMNS.map(col => (
                <th key={col} className="px-2 py-1.5 text-left font-extrabold uppercase tracking-seat text-[10px] whitespace-nowrap">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {hands.map(h => {
              const board = h.board_high_card
                ? `${h.board_high_card}-high${h.board_paired ? ', paired' : ''}${h.board_monotone ? ', mono' : h.board_two_tone ? ', 2-tone' : ''}`
                : '—'
              const bb = fmtBB(h.net_won, h.big_blind)
              const netColor = h.net_won == null ? 'text-ink-dim' : h.net_won >= 0 ? 'text-ink' : 'text-accent-light'
              return (
                <tr
                  key={`${h.hand_id}-${h.player_idx}`}
                  onClick={onRowClick ? () => onRowClick(h) : undefined}
                  className={`border-b border-divider-light text-ink-muted ${
                    onRowClick ? 'cursor-pointer hover:bg-[rgba(243,242,242,.06)]' : ''
                  }`}
                >
                  {tierLabels && (
                    <td className="px-2 py-1 whitespace-nowrap">
                      <span className="border border-divider-strong text-ink-muted font-extrabold text-[9px] uppercase tracking-seat px-1.5 py-0.5">
                        {tierLabels[h.match_tier ?? 0] ?? '?'}
                      </span>
                    </td>
                  )}
                  <td className="px-2 py-1 whitespace-nowrap tabular-nums">{h.hand_id}</td>
                  <td className="px-2 py-1 whitespace-nowrap">{h.player_id}</td>
                  <td className="px-2 py-1 whitespace-nowrap">{h.position ?? '—'}</td>
                  <td className="px-2 py-1 whitespace-nowrap">{h.street}</td>
                  <td className="px-2 py-1 whitespace-nowrap">{h.pot_type ?? '—'}</td>
                  <td className="px-2 py-1 whitespace-nowrap">{h.facing ?? '—'}</td>
                  <td className="px-2 py-1 whitespace-nowrap">{h.spr_bucket ?? '—'}</td>
                  <td className="px-2 py-1 whitespace-nowrap">{board}</td>
                  <td className="px-2 py-1 whitespace-nowrap tabular-nums">{h.stack?.toFixed(2) ?? '—'}</td>
                  <td className="px-2 py-1 whitespace-nowrap tabular-nums">{h.invested?.toFixed(2) ?? '—'}</td>
                  <td className={`px-2 py-1 whitespace-nowrap tabular-nums font-extrabold ${netColor}`}>{bb}</td>
                  <td className="px-2 py-1 whitespace-nowrap">{h.venue}</td>
                  <td className="px-2 py-1 whitespace-nowrap">{h.date ?? '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between px-1 py-2 text-[11px] text-ink-muted tabular-nums">
        <span>{from.toLocaleString()}–{to.toLocaleString()} of {total.toLocaleString()}</span>
        <div className="flex gap-2">
          <button
            onClick={() => onPageChange(Math.max(0, offset - limit))}
            disabled={offset === 0}
            className="font-extrabold text-[10px] tracking-btn uppercase px-2 py-1 border border-divider-strong text-ink hover:bg-[rgba(243,242,242,.1)] disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Prev
          </button>
          <button
            onClick={() => onPageChange(offset + limit)}
            disabled={to >= total}
            className="font-extrabold text-[10px] tracking-btn uppercase px-2 py-1 border border-divider-strong text-ink hover:bg-[rgba(243,242,242,.1)] disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  )
}
