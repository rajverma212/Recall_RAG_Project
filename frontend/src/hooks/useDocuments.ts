import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteDocument, ingestDocument, listDocuments } from '../lib/api'
import type { ChunkingStrategy } from '../lib/types'

export function useDocuments() {
  return useQuery({
    queryKey: ['documents'],
    queryFn: listDocuments,
    refetchInterval: 5000,
  })
}

export function useIngest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ file, strategy }: { file: File; strategy: ChunkingStrategy }) =>
      ingestDocument(file, strategy),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['documents'] })
    },
  })
}

export function useDeleteDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: deleteDocument,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['documents'] })
    },
  })
}
