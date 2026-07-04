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

  const scottyLabel = hasHoleCards ? 'With these cards' : 'ScottyWotty'

  return (
    <div className="bg-white border-2 border-emerald-500 rounded-lg shadow-sm text-gray-900 text-xs w-72">
      <Handle type="target" position={Position.Left} />

      <div className="relative px-3 py-2 border-b border-gray-200 bg-gray-50 rounded-t-[6px] text-center font-semibold text-sm tracking-tight text-gray-900">
        <span>Results</span>
        <button
          onClick={() => deleteNode(id)}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-300 hover:text-red-500 transition-colors text-base leading-none"
          title="Delete node"
        >
          ×
        </button>
      </div>

      {loading && (
        <div className="px-3 py-6 text-center text-gray-400">
          <div className="animate-pulse mb-1">Running query…</div>
          <div className="text-gray-400 text-xs tabular-nums">{elapsed}s — DB cache may be cold</div>
        </div>
      )}

      {error && (
        <div className="px-3 py-3 text-red-500">{error}</div>
      )}

      {!loading && !error && !stats && (
        <div className="px-3 py-4 text-center text-gray-400">No data yet</div>
      )}

      {!loading && !error && stats && (
        <div className="divide-y divide-gray-100">
          {stats.message && (
            <div className="px-3 py-4 text-center text-amber-600 text-xs">{stats.message}</div>
          )}

          {!stats.message && stats.total_hands > 0 && (
            <div className="px-3 py-2 flex gap-4 text-gray-600">
              <span><span className="text-gray-900 font-bold">{stats.total_hands.toLocaleString()}</span> hands</span>
              <span><span className="text-gray-900 font-bold">{stats.showdown_pct}%</span> SD</span>
              <span><span className="text-gray-900 font-bold">{stats.avg_pot_bb}</span> BB pot</span>
            </div>
          )}

          {stats.scotty_hands != null && (
            <div className="px-3 py-2">
              <div className="text-rose-500 font-medium mb-1">{scottyLabel}</div>
              {stats.scotty_hands === 0 ? (
                <div className="text-gray-400">Not in these hands</div>
              ) : (
                <div className="space-y-0.5 text-gray-600">
                  <div className="flex gap-3">
                    <span>
                      <span className="text-gray-900 font-bold">{stats.scotty_hands.toLocaleString()}</span> hands
                    </span>
                    {stats.scotty_won_pct != null && (
                      <span>
                        <span className="text-gray-900 font-bold">{stats.scotty_won_pct}%</span> won
                      </span>
                    )}
                  </div>
                  {stats.scotty_bb_per_100 != null && (
                    <div>
                      <span className={`font-bold font-mono ${stats.scotty_bb_per_100 >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                        {fmtBB(stats.scotty_bb_per_100 / 100)}
                      </span>
                      <span className="text-gray-400"> BB avg per hand</span>
                      <span className="text-gray-400 ml-2">
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
