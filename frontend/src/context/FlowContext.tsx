import { createContext, useContext } from 'react'

interface FlowContextValue {
  runQuery: (nodeId: string) => Promise<void>
  checkSql: (nodeId: string) => Promise<string>
  updateNodeValue: (nodeId: string, value: unknown) => void
  deleteNode: (nodeId: string) => void
}

export const FlowContext = createContext<FlowContextValue>({
  runQuery: async () => {},
  checkSql: async () => '',
  updateNodeValue: () => {},
  deleteNode: () => {},
})

export function useFlow() {
  return useContext(FlowContext)
}
