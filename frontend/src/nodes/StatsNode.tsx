import { Handle, Position, NodeProps } from '@xyflow/react'
import { StatsNodeData, PositionStat } from '../types'
import { useFlow } from '../context/FlowContext'

const POS_ORDER = ['BTN', 'CO', 'HJ', 'UTG', 'SB', 'BB']

function fmtBB(n: number): string {
  return `${n >= 0 ? '+' : ''}${n}`
}

function sortPositions(rows: PositionStat[]): PositionStat[] {
  return [...rows].sort((a, b) => {
    const ai = POS_ORDER.indexOf(a.position)
    const bi = POS_ORDER.indexOf(b.position)
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi)
  })
}

export function StatsNode({ id, data }: NodeProps) {
  const { stats, loading, error } = data as unknown as StatsNodeData
  const { deleteNode } = useFlow()

  return (
    <div className="bg-gray-900 border border-emerald-600 rounded-lg shadow-xl text-white text-xs w-80">
      <Handle type="target" position={Position.Left} />

      <div className="px-3 py-1.5 border-b border-emerald-700 font-semibold text-xs uppercase tracking-wider text-emerald-400 flex items-center justify-between">
        <span>📊 Results</span>
        <button
          onClick={() => deleteNode(id)}
          className="text-gray-600 hover:text-red-400 transition-colors text-base leading-none ml-2"
          title="Delete node"
        >
          ×
        </button>
      </div>

      {loading && (
        <div className="px-3 py-6 text-center text-gray-400 animate-pulse">Running query…</div>
      )}

      {error && (
        <div className="px-3 py-3 text-red-400">{error}</div>
      )}

      {!loading && !error && !stats && (
        <div className="px-3 py-4 text-center text-gray-500">No data yet</div>
      )}

      {!loading && !error && stats && (
        <div className="divide-y divide-gray-800">
          {/* Message (large result set or no filter) */}
          {stats.message && (
            <div className="px-3 py-4 text-center text-amber-400 text-xs">{stats.message}</div>
          )}

          {/* Summary */}
          {!stats.message && stats.total_hands > 0 && (
            <div className="px-3 py-2 flex gap-4 text-gray-200">
              <span><span className="text-white font-bold">{stats.total_hands.toLocaleString()}</span> hands</span>
              <span><span className="text-white font-bold">{stats.showdown_pct}%</span> SD</span>
              <span><span className="text-white font-bold">{stats.avg_pot_bb}</span> BB avg pot</span>
            </div>
          )}

          {/* ScottyWotty */}
          {stats.scotty_hands !== undefined && (
            <div className="px-3 py-2">
              <div className="text-rose-400 font-medium mb-1">👤 ScottyWotty</div>
              {stats.scotty_hands === 0 ? (
                <div className="text-gray-600">Not in these hands</div>
              ) : (
                <div className="flex flex-wrap gap-3 text-gray-200">
                  <span>
                    <span className="text-white font-bold">{stats.scotty_hands.toLocaleString()}</span> hands
                  </span>
                  {stats.scotty_won_pct != null && (
                    <span>
                      <span className="text-white font-bold">{stats.scotty_won_pct}%</span> won
                    </span>
                  )}
                  {stats.scotty_bb_per_100 != null && (
                    <span>
                      <span className={`font-bold font-mono ${stats.scotty_bb_per_100 >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {stats.scotty_bb_per_100 >= 0 ? '+' : ''}{stats.scotty_bb_per_100}
                      </span>
                      {' BB/100'}
                    </span>
                  )}
                </div>
              )}
            </div>
          )}

          {/* BB/100 by position */}
          {stats.by_position.length > 0 && (
            <div className="px-3 py-2">
              <div className="text-gray-500 mb-1 font-medium">BB/100 by position</div>
              <table className="w-full">
                <thead>
                  <tr className="text-gray-500">
                    <th className="text-left font-normal">Pos</th>
                    <th className="text-right font-normal">Hands</th>
                    <th className="text-right font-normal">BB/100</th>
                  </tr>
                </thead>
                <tbody>
                  {sortPositions(stats.by_position).map(row => (
                    <tr key={row.position} className="border-t border-gray-800">
                      <td className="text-gray-300 py-0.5">{row.position}</td>
                      <td className="text-right text-gray-400">{row.hands.toLocaleString()}</td>
                      <td className={`text-right font-mono ${row.bb_per_100 >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {fmtBB(row.bb_per_100)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <Handle type="source" position={Position.Right} />
    </div>
  )
}
