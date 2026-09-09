import { useEffect, useState } from 'react'
import { SpotSummary } from '../types'
import { getSpotsApi } from '../utils/api'

interface Props {
  selectedSpotId: string | null
  onSelect: (spotId: string) => void
}

export function SpotSelector({ selectedSpotId, onSelect }: Props) {
  const [spots, setSpots] = useState<SpotSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getSpotsApi()
      .then(res => { if (!cancelled) setSpots(res) })
      .catch(err => { if (!cancelled) setError(String(err)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  if (loading) return <div className="text-sm text-gray-400 py-2">Loading solved spots…</div>
  if (error) return <div className="text-sm text-red-500 py-2">{error}</div>
  if (spots.length === 0) {
    return (
      <div className="text-sm text-gray-400 py-2">
        No solved spots yet — run cfr_solver/solve.py then cfr_solver/export_strategy.py.
      </div>
    )
  }

  return (
    <div className="overflow-auto border border-gray-200 rounded-md">
      <table className="min-w-full text-xs">
        <thead className="bg-gray-50 border-b border-gray-200">
          <tr>
            <th className="px-2 py-1.5 text-left font-semibold text-gray-600">Spot</th>
            <th className="px-2 py-1.5 text-left font-semibold text-gray-600">Positions</th>
            <th className="px-2 py-1.5 text-left font-semibold text-gray-600">Street</th>
            <th className="px-2 py-1.5 text-left font-semibold text-gray-600">Board</th>
            <th className="px-2 py-1.5 text-left font-semibold text-gray-600">Stack / Pot (BB)</th>
            <th className="px-2 py-1.5 text-left font-semibold text-gray-600"># Bet sizes</th>
            <th className="px-2 py-1.5 text-left font-semibold text-gray-600">Source hands</th>
          </tr>
        </thead>
        <tbody>
          {spots.map(s => (
            <tr
              key={s.spot_id}
              onClick={() => onSelect(s.spot_id)}
              className={`cursor-pointer hover:bg-indigo-50 ${
                selectedSpotId === s.spot_id ? 'bg-indigo-100 font-medium' : 'bg-white'
              }`}
            >
              <td className="px-2 py-1">{s.spot_id}</td>
              <td className="px-2 py-1 whitespace-nowrap">{s.positions}</td>
              <td className="px-2 py-1">{s.street}</td>
              <td className="px-2 py-1 tabular-nums">{s.board}</td>
              <td className="px-2 py-1 tabular-nums whitespace-nowrap">
                {s.effective_stack_bb.toFixed(1)} / {s.pot_bb_at_street_start.toFixed(1)}
              </td>
              <td className="px-2 py-1 tabular-nums">{s.bet_sizes_bb.length}</td>
              <td className="px-2 py-1 tabular-nums">{s.n_matching_hands}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
