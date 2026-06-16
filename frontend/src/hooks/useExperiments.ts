import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createExperiment, listExperiments } from '../lib/api'
import type { Experiment } from '../lib/types'

export function useExperiments() {
  return useQuery({
    queryKey: ['experiments'],
    queryFn: listExperiments,
  })
}

export function useCreateExperiment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Partial<Experiment>) => createExperiment(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['experiments'] })
    },
  })
}
