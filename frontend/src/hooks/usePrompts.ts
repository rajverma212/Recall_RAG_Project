import { useQuery } from '@tanstack/react-query'
import { listPrompts } from '../lib/api'

export function usePrompts() {
  return useQuery({
    queryKey: ['prompts'],
    queryFn: listPrompts,
  })
}
