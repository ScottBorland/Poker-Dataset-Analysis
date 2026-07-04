import { Node, Edge } from '@xyflow/react'
import { ApiFilter } from '../types'

function dropEmpty(filters: ApiFilter[]): ApiFilter[] {
  return filters.filter(f => {
    if (f.value === 'any' || f.value === null || f.value === undefined || f.value === '') return false
    if (Array.isArray(f.value) && f.value.length === 0) return false
    if (f.type === 'player_position') {
      const v = f.value as { player_id?: string; positions?: string[] } | null
      if (!v || !v.positions || v.positions.length === 0) return false
    }
    return true
  })
}

/** Walks backwards from nodeId, collecting every upstream filter node. */
export function getFilterChain(nodeId: string, nodes: Node[], edges: Edge[]): ApiFilter[] {
  const filters: ApiFilter[] = []
  let currentId: string | undefined = nodeId
  const visited = new Set<string>()

  while (currentId && !visited.has(currentId)) {
    visited.add(currentId)
    const node = nodes.find(n => n.id === currentId)
    if (!node) break

    if (node.type !== 'stats') {
      filters.unshift({
        type: node.data.type as string,
        value: node.data.value,
      })
    }

    const incoming = edges.find(e => e.target === currentId)
    currentId = incoming?.source
  }

  return dropEmpty(filters)
}

/** Walks the entire connected chain (upstream + downstream) from nodeId. */
export function getFullFilterChain(nodeId: string, nodes: Node[], edges: Edge[]): ApiFilter[] {
  // 1. Walk backward to find the start of the chain.
  let startId = nodeId
  const back = new Set<string>()
  while (!back.has(startId)) {
    back.add(startId)
    const incoming = edges.find(e => e.target === startId)
    if (!incoming) break
    startId = incoming.source
  }

  // 2. Walk forward from the start, collecting every filter node in order.
  const filters: ApiFilter[] = []
  let currentId: string | undefined = startId
  const fwd = new Set<string>()
  while (currentId && !fwd.has(currentId)) {
    fwd.add(currentId)
    const node = nodes.find(n => n.id === currentId)
    if (!node) break

    if (node.type !== 'stats') {
      filters.push({
        type: node.data.type as string,
        value: node.data.value,
      })
    }

    const outgoing = edges.find(e => e.source === currentId)
    currentId = outgoing?.target
  }

  return dropEmpty(filters)
}
