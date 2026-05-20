import type { ReactNode } from 'react'
import { Handle, Position } from '@xyflow/react'
import { useFlow } from '../context/FlowContext'

interface Props {
  id: string
  title: string
  accent: string
  children: ReactNode
}

export function FilterNodeWrapper({ id, title, accent, children }: Props) {
  const { runQuery, deleteNode } = useFlow()

  return (
    <div className={`bg-gray-900 border ${accent} rounded-lg shadow-lg w-52 text-white text-sm`}>
      <Handle type="target" position={Position.Left} />

      <div className={`px-3 py-1.5 border-b ${accent} font-semibold text-xs uppercase tracking-wider text-gray-300 flex items-center justify-between`}>
        <span>{title}</span>
        <button
          onClick={() => deleteNode(id)}
          className="text-gray-600 hover:text-red-400 transition-colors text-base leading-none ml-2"
          title="Delete node"
        >
          ×
        </button>
      </div>

      <div className="px-3 py-2 space-y-2">
        {children}
      </div>

      <div className="px-3 pb-3">
        <button
          onClick={() => runQuery(id)}
          className="w-full mt-1 py-1 rounded bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700 text-xs font-medium transition-colors"
        >
          ▶ Run Query
        </button>
      </div>

      <Handle type="source" position={Position.Right} />
    </div>
  )
}
