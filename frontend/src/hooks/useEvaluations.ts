import { useQuery } from '@tanstack/react-query'
import { getEvaluation, listEvaluations } from '../lib/api'

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
