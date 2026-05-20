import { NodeProps } from '@xyflow/react'
import { FilterNodeWrapper } from './FilterNodeWrapper'
import { useFlow } from '../context/FlowContext'

type ShowdownValue = 'any' | 'yes' | 'no'
const OPTIONS: ShowdownValue[] = ['any', 'yes', 'no']

export function ShowdownNode({ id, data }: NodeProps) {
  const { updateNodeValue } = useFlow()
  const value = (data.value as ShowdownValue) ?? 'any'

  return (
    <FilterNodeWrapper id={id} title="🎯 Showdown" accent="border-teal-500">
      <div className="flex rounded overflow-hidden border border-gray-700">
        {OPTIONS.map(opt => (
          <button
            key={opt}
            onClick={() => updateNodeValue(id, opt)}
            className={`flex-1 py-1 text-xs font-medium transition-colors capitalize ${
              value === opt
                ? 'bg-teal-600 text-white'
                : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
            }`}
          >
            {opt}
          </button>
        ))}
      </div>
    </FilterNodeWrapper>
  )
}
