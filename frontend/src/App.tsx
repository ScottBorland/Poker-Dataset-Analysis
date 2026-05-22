import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ReactFlow,
  addEdge,
  useNodesState,
  useEdgesState,
  Controls,
  Background,
  BackgroundVariant,
  Connection,
  Node,
  Edge,
  ReactFlowInstance,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import { nodeTypes } from './nodes'
import { NodePalette } from './components/NodePalette'
import { FlowContext } from './context/FlowContext'
import { getFilterChain } from './utils/chainTraversal'
import { runQueryApi } from './utils/api'
import { StatsNodeData } from './types'

let _idCounter = 0
function uid(prefix: string) {
  return `${prefix}-${++_idCounter}`
}

const DEFAULT_VALUES: Record<string, unknown> = {
  numPlayers: 'any',
  holeCards: [],
  showdown: 'any',
  flopType: [],
  preflopAction: [],
  playerName: 'ScottyWotty',
  playerPosition: { player_id: '', positions: [] },
  venue: 'any',
}

const API_TYPES: Record<string, string> = {
  numPlayers: 'num_players',
  holeCards: 'hole_cards',
  showdown: 'showdown',
  flopType: 'flop_type',
  preflopAction: 'preflop_action',
  playerName: 'player',
  playerPosition: 'player_position',
  venue: 'venue',
}

export default function App() {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [rfInstance, setRfInstance] = useState<ReactFlowInstance | null>(null)
  const wrapperRef = useRef<HTMLDivElement>(null)

  // Stable refs so callbacks always see current state
  const nodesRef = useRef(nodes)
  const edgesRef = useRef(edges)
  useEffect(() => { nodesRef.current = nodes }, [nodes])
  useEffect(() => { edgesRef.current = edges }, [edges])

  const updateNodeValue = useCallback((nodeId: string, value: unknown) => {
    setNodes(nds => nds.map(n =>
      n.id === nodeId ? { ...n, data: { ...n.data, value } } : n
    ))
  }, [setNodes])

  const deleteNode = useCallback((nodeId: string) => {
    setNodes(nds => nds.filter(n => n.id !== nodeId))
    setEdges(eds => eds.filter(e => e.source !== nodeId && e.target !== nodeId))
  }, [setNodes, setEdges])

  const runQuery = useCallback(async (nodeId: string) => {
    const currentNodes = nodesRef.current
    const currentEdges = edgesRef.current
    const filters = getFilterChain(nodeId, currentNodes, currentEdges)

    const hasHoleCards = filters.some(
      f => f.type === 'hole_cards' && Array.isArray(f.value) && (f.value as string[]).length > 0
    )

    const clickedNode = currentNodes.find(n => n.id === nodeId)
    if (!clickedNode) return

    // Check for existing Stats node directly after this node
    const outEdge = currentEdges.find(e => e.source === nodeId)
    const nextNode = outEdge ? currentNodes.find(n => n.id === outEdge.target) : null

    let statsId: string

    if (nextNode?.type === 'stats') {
      // Update existing Stats node in place
      statsId = nextNode.id
      setNodes(nds => nds.map(n =>
        n.id === statsId
          ? { ...n, data: { stats: null, loading: true, error: null, hasHoleCards } satisfies StatsNodeData }
          : n
      ))
    } else {
      // Create new Stats node, inserting it between current and next
      statsId = uid('stats')
      const statsPos = {
        x: clickedNode.position.x + 260,
        y: clickedNode.position.y,
      }
      const statsNode: Node = {
        id: statsId,
        type: 'stats',
        position: statsPos,
        data: { stats: null, loading: true, error: null, hasHoleCards } satisfies StatsNodeData,
      }

      if (outEdge) {
        // Insert stats between current node and its successor
        setEdges(eds => [
          ...eds.filter(e => e.id !== outEdge.id),
          { id: uid('e'), source: nodeId, target: statsId },
          { id: uid('e'), source: statsId, target: outEdge.target },
        ])
      } else {
        setEdges(eds => [...eds, { id: uid('e'), source: nodeId, target: statsId }])
      }

      setNodes(nds => [...nds, statsNode])
    }

    try {
      const result = await runQueryApi(filters)
      setNodes(nds => nds.map(n =>
        n.id === statsId
          ? { ...n, data: { stats: result, loading: false, error: null, hasHoleCards } satisfies StatsNodeData }
          : n
      ))
    } catch (err) {
      setNodes(nds => nds.map(n =>
        n.id === statsId
          ? { ...n, data: { stats: null, loading: false, error: String(err), hasHoleCards } satisfies StatsNodeData }
          : n
      ))
    }
  }, [setNodes, setEdges])

  const contextValue = useMemo(() => ({ runQuery, updateNodeValue, deleteNode }), [runQuery, updateNodeValue, deleteNode])

  const onConnect = useCallback((connection: Connection) => {
    setEdges(eds => addEdge({ ...connection, animated: true }, eds))
  }, [setEdges])

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    const nodeType = e.dataTransfer.getData('application/reactflow')
    if (!nodeType || !rfInstance) return

    const position = rfInstance.screenToFlowPosition({ x: e.clientX, y: e.clientY })

    const defaultValue = DEFAULT_VALUES[nodeType] ?? 'any'
    const newNode: Node = {
      id: uid(nodeType),
      type: nodeType,
      position,
      data: {
        type: API_TYPES[nodeType],
        value: Array.isArray(defaultValue) ? [] : defaultValue,
      },
    }
    setNodes(nds => [...nds, newNode])
  }, [rfInstance, setNodes])

  return (
    <FlowContext.Provider value={contextValue}>
      <div className="flex h-screen w-screen overflow-hidden bg-gray-950">
        <NodePalette />
        <div ref={wrapperRef} className="flex-1 h-full">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onInit={setRfInstance}
            onDrop={onDrop}
            onDragOver={onDragOver}
            nodeTypes={nodeTypes}
            fitView
            defaultEdgeOptions={{
              animated: true,
              style: { stroke: '#4f46e5', strokeWidth: 2 },
            }}
          >
            <Controls />
            <Background variant={BackgroundVariant.Dots} color="#1f2937" gap={24} size={1} />
          </ReactFlow>
        </div>
      </div>
    </FlowContext.Provider>
  )
}
