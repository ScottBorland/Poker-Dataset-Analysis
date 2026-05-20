import { NodeProps } from '@xyflow/react'
import { FilterNodeWrapper } from './FilterNodeWrapper'
import { useFlow } from '../context/FlowContext'

const OPTIONS = [
  { value: 'any', label: 'Any' },
  { value: 'rfi', label: 'RFI (raise first in)' },
  { value: 'single_raised_pot', label: 'Single raised pot' },
  { value: '3bet_pot', label: '3-bet pot' },
  { value: '4bet_pot', label: '4-bet pot' },
  { value: '5bet_pot', label: '5-bet pot' },
  { value: 'squeeze', label: 'Squeeze' },
  { value: 'limp_pot', label: 'Limp pot' },
  { value: 'blind_vs_blind', label: 'Blind vs blind' },
  { value: 'all_in_preflop', label: 'All-in preflop' },
]

export function PreflopActionNode({ id, data }: NodeProps) {
  const { updateNodeValue } = useFlow()
  const value = (data.value as string) ?? 'any'

  return (
    <FilterNodeWrapper id={id} title="♠ Preflop Action" accent="border-blue-500">
      <select
        value={value}
        onChange={e => updateNodeValue(id, e.target.value)}
        className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-xs focus:outline-none focus:border-blue-400"
      >
        {OPTIONS.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </FilterNodeWrapper>
  )
}
