import { useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getEvaluation,
  getEvaluationStatus,
  listEvaluations,
  startEvaluation,
} from '../lib/api'
import type { EvaluationRunRequest } from '../lib/types'

export function useEvaluations() {
  return useQuery({
    queryKey: ['evaluations'],
    queryFn: listEvaluations,
  })
}

export function useEvaluation(id: string | null) {
  return useQuery({
    queryKey: ['evaluations', id],
    queryFn: () => getEvaluation(id!),
    enabled: id !== null,
  })
}

/**
 * Polls the background-run job status. While a run is in progress we poll every
 * 2s; when idle/done/error we stop polling. When a run transitions to "done"
 * the run list is refetched so the new run appears without a manual refresh.
 */
export function useEvaluationJob() {
  const qc = useQueryClient()
  const query = useQuery({
    queryKey: ['evaluation-status'],
    queryFn: getEvaluationStatus,
    refetchInterval: (q) => (q.state.data?.status === 'running' ? 2000 : false),
  })

  // When a run finishes, refetch the run list once so the new run appears.
  const prevStatus = useRef<string | undefined>(undefined)
  const status = query.data?.status
  useEffect(() => {
    if (prevStatus.current === 'running' && status === 'done') {
      qc.invalidateQueries({ queryKey: ['evaluations'] })
    }
    prevStatus.current = status
  }, [status, qc])

  return query
}

export function useStartEvaluation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body?: EvaluationRunRequest) => startEvaluation(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['evaluation-status'] })
    },
  })
}
