import { NodeProps } from '@xyflow/react'
import { FilterNodeWrapper } from './FilterNodeWrapper'
import { useFlow } from '../context/FlowContext'

const OPTIONS = [
  { value: 'any', label: 'Any venue' },
  { value: 'absolute_poker', label: 'Absolute Poker (~777k hands)' },
  { value: '888poker', label: '888poker (~118k hands)' },
]

export function VenueNode({ id, data }: NodeProps) {
  const { updateNodeValue } = useFlow()
  const value = (data.value as string) ?? 'any'

  return (
    <FilterNodeWrapper id={id} title="Venue" accent="border-indigo-400">
      <select
        value={value}
        onChange={e => updateNodeValue(id, e.target.value)}
        className="w-full bg-white border border-gray-300 rounded px-2 py-1 text-gray-900 text-xs focus:outline-none focus:border-indigo-400"
      >
        {OPTIONS.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      {value === '888poker' && (
        <div className="text-gray-400 text-xs">Includes ScottyWotty sessions.</div>
      )}
      {value === 'absolute_poker' && (
        <div className="text-gray-400 text-xs">Population study only — no hero stats.</div>
      )}
    </FilterNodeWrapper>
  )
}
