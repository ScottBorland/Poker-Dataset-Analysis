import { createContext, useContext } from 'react'

interface FlowContextValue {
  runQuery: (nodeId: string) => Promise<void>
  updateNodeValue: (nodeId: string, value: unknown) => void
  deleteNode: (nodeId: string) => void
}

export const FlowContext = createContext<FlowContextValue>({
  runQuery: async () => {},
  updateNodeValue: () => {},
  deleteNode: () => {},
})

export function useFlow() {
  return useContext(FlowContext)
}
