import { NodeProps } from '@xyflow/react'
import { FilterNodeWrapper } from './FilterNodeWrapper'
import { useFlow } from '../context/FlowContext'

const OPTIONS = [
  { value: 'rfi', label: 'RFI' },
  { value: 'single_raised_pot', label: 'Single raised' },
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
  const selected: string[] = Array.isArray(data.value) ? (data.value as string[]) : []

  function toggle(val: string) {
    const next = selected.includes(val)
      ? selected.filter(v => v !== val)
      : [...selected, val]
    updateNodeValue(id, next)
  }

  return (
    <FilterNodeWrapper id={id} title="♠ Preflop Action" accent="border-blue-500">
      <div className="grid grid-cols-2 gap-x-2 gap-y-0.5">
        {OPTIONS.map(o => (
          <label key={o.value} className="flex items-center gap-1.5 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={selected.includes(o.value)}
              onChange={() => toggle(o.value)}
              className="accent-blue-500 shrink-0"
            />
            <span className="text-gray-300 text-xs">{o.label}</span>
          </label>
        ))}
      </div>
      {selected.length === 0 && (
        <div className="text-gray-600 text-xs">No filter (select one or more).</div>
      )}
      {selected.length > 1 && (
        <div className="text-blue-700 text-xs">{selected.length} selected — OR logic.</div>
      )}
    </FilterNodeWrapper>
  )
}
