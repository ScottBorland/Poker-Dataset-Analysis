import { NodeProps } from '@xyflow/react'
import { FilterNodeWrapper } from './FilterNodeWrapper'
import { useFlow } from '../context/FlowContext'

const GROUPS = [
  {
    label: 'Suit',
    options: [
      { value: 'flop_rainbow', label: 'Rainbow' },
      { value: 'flop_two_tone', label: 'Two-tone' },
      { value: 'flop_monotone', label: 'Monotone' },
    ],
  },
  {
    label: 'Board',
    options: [
      { value: 'flop_ace_high', label: 'Ace-high' },
      { value: 'flop_king_high', label: 'King-high' },
      { value: 'flop_low', label: 'Low (≤9)' },
      { value: 'flop_two_broadway', label: 'Two broadway' },
      { value: 'flop_paired', label: 'Paired' },
    ],
  },
  {
    label: 'Structure',
    options: [
      { value: 'flop_connected', label: 'Connected' },
      { value: 'flop_dry', label: 'Dry' },
    ],
  },
]

export function FlopTypeNode({ id, data }: NodeProps) {
  const { updateNodeValue } = useFlow()
  const selected: string[] = Array.isArray(data.value) ? (data.value as string[]) : []

  function toggle(val: string) {
    const next = selected.includes(val)
      ? selected.filter(v => v !== val)
      : [...selected, val]
    updateNodeValue(id, next)
  }

  return (
    <FilterNodeWrapper id={id} title="🂠 Flop Type" accent="border-green-500">
      <div className="space-y-2">
        {GROUPS.map(group => (
          <div key={group.label}>
            <div className="text-gray-600 text-xs mb-0.5 uppercase tracking-wider">{group.label}</div>
            <div className="grid grid-cols-2 gap-x-2 gap-y-0.5">
              {group.options.map(o => (
                <label key={o.value} className="flex items-center gap-1.5 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={selected.includes(o.value)}
                    onChange={() => toggle(o.value)}
                    className="accent-green-500 shrink-0"
                  />
                  <span className="text-gray-300 text-xs">{o.label}</span>
                </label>
              ))}
            </div>
          </div>
        ))}
      </div>
      {selected.length === 0 && (
        <div className="text-gray-600 text-xs">No filter (select one or more).</div>
      )}
      {selected.length > 1 && (
        <div className="text-green-700 text-xs">{selected.length} selected — AND logic.</div>
      )}
    </FilterNodeWrapper>
  )
}
