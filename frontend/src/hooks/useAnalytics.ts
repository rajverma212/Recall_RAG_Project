import { useQuery } from '@tanstack/react-query'
import { getAnalytics } from '../lib/api'

export function useAnalytics() {
  return useQuery({
    queryKey: ['analytics'],
    queryFn: getAnalytics,
    refetchInterval: 30_000,
  })
}
