import { createContext, useContext, useState, type ReactNode } from 'react'
import { useAsk, useStreamingAsk } from '../hooks'

// Holds the Ask page's query state above the router so that results, the
// in-flight question, and UI toggles survive navigation to other tabs. Without
// this, AskPage unmounts on route change and its local state (the answer) is
// discarded, making a completed query vanish when the user comes back.
interface AskContextValue {
  question: string
  setQuestion: (q: string) => void
  streaming: boolean
  setStreaming: React.Dispatch<React.SetStateAction<boolean>>
  activeMarker: number | null
  setActiveMarker: (m: number | null) => void
  askMutation: ReturnType<typeof useAsk>
  streamState: ReturnType<typeof useStreamingAsk>
}

const AskContext = createContext<AskContextValue | null>(null)

export function AskProvider({ children }: { children: ReactNode }) {
  const [question, setQuestion] = useState('')
  const [streaming, setStreaming] = useState(true)
  const [activeMarker, setActiveMarker] = useState<number | null>(null)
  const askMutation = useAsk()
  const streamState = useStreamingAsk()

  return (
    <AskContext.Provider
      value={{
        question,
        setQuestion,
        streaming,
        setStreaming,
        activeMarker,
        setActiveMarker,
        askMutation,
        streamState,
      }}
    >
      {children}
    </AskContext.Provider>
  )
}

export function useAskContext() {
  const ctx = useContext(AskContext)
  if (!ctx) throw new Error('useAskContext must be used within an AskProvider')
  return ctx
}
