import { Handle, Position, NodeProps } from '@xyflow/react'
import { useEffect, useRef, useState } from 'react'
import { StatsNodeData } from '../types'
import { useFlow } from '../context/FlowContext'

function fmtBB(n: number): string {
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}`
}

export function StatsNode({ id, data }: NodeProps) {
  const { stats, loading, error, hasHoleCards } = data as unknown as StatsNodeData
  const { deleteNode } = useFlow()
  const [elapsed, setElapsed] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (loading) {
      setElapsed(0)
      timerRef.current = setInterval(() => setElapsed(s => s + 1), 1000)
    } else {
      if (timerRef.current) clearInterval(timerRef.current)
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [loading])

  const scottyLabel = hasHoleCards ? '🃏 With these cards' : '👤 ScottyWotty'

  return (
    <div className="bg-gray-900 border border-emerald-600 rounded-lg shadow-xl text-white text-xs w-72">
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
        <div className="px-3 py-6 text-center text-gray-400">
          <div className="animate-pulse mb-1">Running query…</div>
          <div className="text-gray-600 text-xs tabular-nums">{elapsed}s — DB cache may be cold</div>
        </div>
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
              <span><span className="text-white font-bold">{stats.avg_pot_bb}</span> BB pot</span>
            </div>
          )}

          {/* Card holder / ScottyWotty stats */}
          {stats.scotty_hands != null && (
            <div className="px-3 py-2">
              <div className="text-rose-400 font-medium mb-1">{scottyLabel}</div>
              {stats.scotty_hands === 0 ? (
                <div className="text-gray-600">Not in these hands</div>
              ) : (
                <div className="space-y-0.5 text-gray-200">
                  <div className="flex gap-3">
                    <span>
                      <span className="text-white font-bold">{stats.scotty_hands.toLocaleString()}</span> hands
                    </span>
                    {stats.scotty_won_pct != null && (
                      <span>
                        <span className="text-white font-bold">{stats.scotty_won_pct}%</span> won
                      </span>
                    )}
                  </div>
                  {stats.scotty_bb_per_100 != null && (
                    <div>
                      <span className={`font-bold font-mono ${stats.scotty_bb_per_100 >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {fmtBB(stats.scotty_bb_per_100 / 100)}
                      </span>
                      <span className="text-gray-500"> BB avg per hand</span>
                      <span className="text-gray-600 ml-2">
                        ({stats.scotty_bb_per_100 >= 0 ? '+' : ''}{stats.scotty_bb_per_100} BB/100)
                      </span>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <Handle type="source" position={Position.Right} />
    </div>
  )
}
