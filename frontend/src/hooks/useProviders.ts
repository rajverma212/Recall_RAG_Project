import { useQuery } from '@tanstack/react-query'
import { getProviders } from '../lib/api'

export function useProviders() {
  return useQuery({
    queryKey: ['providers'],
    queryFn: getProviders,
    refetchInterval: 30_000,
  })
}
