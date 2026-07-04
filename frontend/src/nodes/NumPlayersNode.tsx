import { NodeProps } from '@xyflow/react'
import { FilterNodeWrapper } from './FilterNodeWrapper'
import { useFlow } from '../context/FlowContext'

const OPTIONS = ['any', '2', '3', '4', '5', '6', '7', '8', '9'] as const

export function NumPlayersNode({ id, data }: NodeProps) {
  const { updateNodeValue } = useFlow()
  const value = (data.value as string) ?? 'any'

  return (
    <FilterNodeWrapper id={id} title="Players" accent="border-orange-400">
      <select
        value={value}
        onChange={e => updateNodeValue(id, e.target.value === 'any' ? 'any' : Number(e.target.value))}
        className="w-full bg-white border border-gray-300 rounded px-2 py-1 text-gray-900 text-xs focus:outline-none focus:border-orange-400"
      >
        {OPTIONS.map(o => (
          <option key={o} value={o}>{o === 'any' ? 'Any' : `${o} players`}</option>
        ))}
      </select>
    </FilterNodeWrapper>
  )
}
