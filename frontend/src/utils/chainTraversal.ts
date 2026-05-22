import { Node, Edge } from '@xyflow/react'
import { ApiFilter } from '../types'

export function getFilterChain(nodeId: string, nodes: Node[], edges: Edge[]): ApiFilter[] {
  const filters: ApiFilter[] = []
  let currentId: string | undefined = nodeId
  const visited = new Set<string>()

  while (currentId && !visited.has(currentId)) {
    visited.add(currentId)
    const node = nodes.find(n => n.id === currentId)
    if (!node) break

    // Skip stats nodes in the chain — they're display-only
    if (node.type !== 'stats') {
      filters.unshift({
        type: node.data.type as string,
        value: node.data.value,
      })
    }

    const incoming = edges.find(e => e.target === currentId)
    currentId = incoming?.source
  }

  // Drop filters that are in their default "any" / empty state
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
