import { NodeProps } from '@xyflow/react'
import { FilterNodeWrapper } from './FilterNodeWrapper'
import { useFlow } from '../context/FlowContext'

export function PlayerNode({ id, data }: NodeProps) {
  const { updateNodeValue } = useFlow()
  const value = (data.value as string) ?? 'ScottyWotty'

  return (
    <FilterNodeWrapper id={id} title="Player" accent="border-rose-400">
      <input
        type="text"
        value={value}
        onChange={e => updateNodeValue(id, e.target.value)}
        placeholder="player_id (e.g. ScottyWotty)"
        className="w-full bg-white border border-gray-300 rounded px-2 py-1 text-gray-900 text-xs
                   placeholder-gray-400 focus:outline-none focus:border-rose-400"
      />
      <div className="text-gray-400 text-xs leading-tight">
        Filters to hands where this player participated.
      </div>
    </FilterNodeWrapper>
  )
}
