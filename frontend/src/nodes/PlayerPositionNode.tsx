import { NodeProps } from '@xyflow/react'
import { FilterNodeWrapper } from './FilterNodeWrapper'
import { useFlow } from '../context/FlowContext'

const POSITIONS = ['BTN', 'CO', 'HJ', 'UTG', 'SB', 'BB']

interface PositionValue {
  player_id: string
  positions: string[]
}

export function PlayerPositionNode({ id, data }: NodeProps) {
  const { updateNodeValue } = useFlow()
  const value = (data.value as PositionValue) ?? { player_id: '', positions: [] }

  function setPlayerId(player_id: string) {
    updateNodeValue(id, { ...value, player_id })
  }

  function togglePosition(pos: string) {
    const positions = value.positions.includes(pos)
      ? value.positions.filter(p => p !== pos)
      : [...value.positions, pos]
    updateNodeValue(id, { ...value, positions })
  }

  return (
    <FilterNodeWrapper id={id} title="Position" accent="border-yellow-400">
      <input
        type="text"
        value={value.player_id}
        onChange={e => setPlayerId(e.target.value)}
        placeholder="player_id (empty = any player)"
        className="w-full bg-white border border-gray-300 rounded px-2 py-1 text-gray-900 text-xs
                   placeholder-gray-400 focus:outline-none focus:border-yellow-400"
      />
      <div className="grid grid-cols-3 gap-x-2 gap-y-0.5 mt-1">
        {POSITIONS.map(p => (
          <label key={p} className="flex items-center gap-1.5 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={value.positions.includes(p)}
              onChange={() => togglePosition(p)}
              className="accent-yellow-500 shrink-0"
            />
            <span className="text-gray-700 text-xs">{p}</span>
          </label>
        ))}
      </div>
      <div className="text-gray-400 text-xs leading-tight">
        {value.positions.length === 0
          ? 'Select positions to filter.'
          : `${value.positions.join(', ')}${value.player_id.trim() ? ` (${value.player_id.trim()})` : ''} — OR logic.`}
      </div>
    </FilterNodeWrapper>
  )
}
