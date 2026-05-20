import { NodeProps } from '@xyflow/react'
import { FilterNodeWrapper } from './FilterNodeWrapper'
import { useFlow } from '../context/FlowContext'

export function PlayerNode({ id, data }: NodeProps) {
  const { updateNodeValue } = useFlow()
  const value = (data.value as string) ?? 'ScottyWotty'

  return (
    <FilterNodeWrapper id={id} title="🙋 Player" accent="border-rose-500">
      <input
        type="text"
        value={value}
        onChange={e => updateNodeValue(id, e.target.value)}
        placeholder="player_id (e.g. ScottyWotty)"
        className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-xs
                   placeholder-gray-600 focus:outline-none focus:border-rose-400"
      />
      <div className="text-gray-600 text-xs leading-tight">
        Filters to hands where this player participated.
      </div>
    </FilterNodeWrapper>
  )
}
