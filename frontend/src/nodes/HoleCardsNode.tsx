import { useRef, useState } from 'react'
import { NodeProps } from '@xyflow/react'
import { FilterNodeWrapper } from './FilterNodeWrapper'
import { useFlow } from '../context/FlowContext'
import { HoleCardGrid } from '../components/HoleCardGrid'

export function HoleCardsNode({ id, data }: NodeProps) {
  const { updateNodeValue } = useFlow()
  const [gridOpen, setGridOpen] = useState(false)
  const btnRef = useRef<HTMLButtonElement>(null)

  const selected = (data.value as string[]) ?? []

  function summary() {
    if (selected.length === 0) return 'None selected'
    if (selected.length <= 3) return selected.join(', ')
    return `${selected.slice(0, 3).join(', ')} +${selected.length - 3}`
  }

  return (
    <FilterNodeWrapper id={id} title="Hole Cards" accent="border-purple-400">
      <button
        ref={btnRef}
        onClick={() => setGridOpen(v => !v)}
        className="w-full bg-white border border-gray-300 rounded px-2 py-1 text-left text-xs text-gray-700 hover:border-purple-400 transition-colors"
      >
        {summary()}
      </button>

      {gridOpen && btnRef.current && (
        <HoleCardGrid
          selected={selected}
          onChange={hands => updateNodeValue(id, hands)}
          onClose={() => setGridOpen(false)}
          anchorRect={btnRef.current.getBoundingClientRect()}
        />
      )}
    </FilterNodeWrapper>
  )
}
