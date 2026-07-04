import { useState, type ReactNode } from 'react'
import { Handle, Position } from '@xyflow/react'
import { useFlow } from '../context/FlowContext'

interface Props {
  id: string
  title: string
  accent: string
  children: ReactNode
}

export function FilterNodeWrapper({ id, title, accent, children }: Props) {
  const { runQuery, checkSql, deleteNode } = useFlow()
  const [sql, setSql] = useState<string | null>(null)
  const [sqlLoading, setSqlLoading] = useState(false)
  const [sqlError, setSqlError] = useState<string | null>(null)

  async function handleCheckSql() {
    setSqlLoading(true)
    setSql(null)
    setSqlError(null)
    try {
      const result = await checkSql(id)
      setSql(result)
    } catch (err) {
      setSqlError(String(err))
    } finally {
      setSqlLoading(false)
    }
  }

  return (
    <div className={`bg-white border-2 ${accent} rounded-lg shadow-sm w-52 text-gray-900 text-sm`}>
      <Handle type="target" position={Position.Left} />

      <div className="relative px-3 py-2 border-b border-gray-200 bg-gray-50 rounded-t-[6px] text-center font-semibold text-sm tracking-tight text-gray-900">
        <span>{title}</span>
        <button
          onClick={() => deleteNode(id)}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-300 hover:text-red-500 transition-colors text-base leading-none"
          title="Delete node"
        >
          ×
        </button>
      </div>

      <div className="px-3 py-2 space-y-2">
        {children}
      </div>

      <div className="px-3 pb-3 space-y-1.5">
        <button
          onClick={() => runQuery(id)}
          className="w-full mt-1 py-1 rounded bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700 text-xs font-medium text-white transition-colors"
        >
          Run Query
        </button>
        <button
          onClick={handleCheckSql}
          disabled={sqlLoading}
          className="w-full py-1 rounded border border-gray-300 bg-white hover:bg-gray-50 active:bg-gray-100 text-xs font-medium text-gray-600 transition-colors disabled:opacity-50"
        >
          {sqlLoading ? 'Loading…' : 'Check SQL Command'}
        </button>
        {sqlError !== null && (
          <div className="mt-1 p-2 bg-red-50 border border-red-200 rounded text-xs text-red-600">
            {sqlError}
          </div>
        )}
        {sql !== null && (
          <pre className="mt-1 p-2 bg-gray-50 border border-gray-200 rounded text-xs text-gray-700 whitespace-pre-wrap break-all leading-relaxed font-mono">
            {sql}
          </pre>
        )}
      </div>

      <Handle type="source" position={Position.Right} />
    </div>
  )
}
