import { NodeProps } from '@xyflow/react'
import { FilterNodeWrapper } from './FilterNodeWrapper'
import { useFlow } from '../context/FlowContext'

const POSITIONS = ['BTN', 'CO', 'HJ', 'UTG', 'SB', 'BB']

interface PositionValue {
  player_id: string
  position: string
}

export function PlayerPositionNode({ id, data }: NodeProps) {
  const { updateNodeValue } = useFlow()
  const value = (data.value as PositionValue) ?? { player_id: 'ScottyWotty', position: 'any' }

  function patch(update: Partial<PositionValue>) {
    updateNodeValue(id, { ...value, ...update })
  }

  return (
    <FilterNodeWrapper id={id} title="🪑 Position" accent="border-yellow-500">
      <input
        type="text"
        value={value.player_id}
        onChange={e => patch({ player_id: e.target.value })}
        placeholder="player_id (empty = any player)"
        className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-xs
                   placeholder-gray-600 focus:outline-none focus:border-yellow-400"
      />
      <select
        value={value.position}
        onChange={e => patch({ position: e.target.value })}
        className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-xs focus:outline-none focus:border-yellow-400"
      >
        <option value="any">Any position</option>
        {POSITIONS.map(p => (
          <option key={p} value={p}>{p}</option>
        ))}
      </select>
      <div className="text-gray-600 text-xs leading-tight">
        {value.position === 'any'
          ? 'Select a position to filter.'
          : value.player_id.trim()
            ? `Hands where ${value.player_id.trim()} was at ${value.position}.`
            : `Hands where any player was at ${value.position}.`}
      </div>
    </FilterNodeWrapper>
  )
}
