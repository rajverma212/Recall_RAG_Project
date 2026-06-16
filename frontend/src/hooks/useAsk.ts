import { useMutation } from '@tanstack/react-query'
import { useCallback, useRef, useState } from 'react'
import { ask, askStream } from '../lib/api'
import type { AskRequest, AskResponse } from '../lib/types'

export function useAsk() {
  return useMutation<AskResponse, Error, AskRequest>({
    mutationFn: ask,
  })
}

export interface StreamingState {
  streaming: boolean
  tokens: string
  response: AskResponse | null
  error: Error | null
  submit: (req: AskRequest) => void
  reset: () => void
}

export function useStreamingAsk(): StreamingState {
  const [streaming, setStreaming] = useState(false)
  const [tokens, setTokens] = useState('')
  const [response, setResponse] = useState<AskResponse | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const abortRef = useRef(false)

  const reset = useCallback(() => {
    abortRef.current = true
    setStreaming(false)
    setTokens('')
    setResponse(null)
    setError(null)
  }, [])

  const submit = useCallback(async (req: AskRequest) => {
    abortRef.current = false
    setStreaming(true)
    setTokens('')
    setResponse(null)
    setError(null)
    try {
      for await (const event of askStream(req)) {
        if (abortRef.current) break
        if (event.type === 'token') {
          setTokens((t) => t + event.text)
        } else if (event.type === 'done') {
          setResponse(event.data)
        }
      }
    } catch (e) {
      if (!abortRef.current) {
        setError(e instanceof Error ? e : new Error(String(e)))
      }
    } finally {
      setStreaming(false)
    }
  }, [])

  return { streaming, tokens, response, error, submit, reset }
}
