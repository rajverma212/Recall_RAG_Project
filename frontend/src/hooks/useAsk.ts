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
  const controllerRef = useRef<AbortController | null>(null)

  const reset = useCallback(() => {
    controllerRef.current?.abort()
    controllerRef.current = null
    setStreaming(false)
    setTokens('')
    setResponse(null)
    setError(null)
  }, [])

  const submit = useCallback(async (req: AskRequest) => {
    controllerRef.current?.abort() // cancel any in-flight stream first
    const controller = new AbortController()
    controllerRef.current = controller
    setStreaming(true)
    setTokens('')
    setResponse(null)
    setError(null)
    try {
      for await (const event of askStream(req, controller.signal)) {
        if (controller.signal.aborted) break
        if (event.type === 'token') {
          setTokens((t) => t + event.text)
        } else if (event.type === 'done') {
          setResponse(event.data)
        }
      }
    } catch (e) {
      // An intentional abort surfaces as an AbortError — not a real failure.
      if (!controller.signal.aborted) {
        setError(e instanceof Error ? e : new Error(String(e)))
      }
    } finally {
      // Only the latest stream owns the shared UI state; a preempted one bows out.
      if (controllerRef.current === controller) {
        controllerRef.current = null
        setStreaming(false)
      }
    }
  }, [])

  return { streaming, tokens, response, error, submit, reset }
}
