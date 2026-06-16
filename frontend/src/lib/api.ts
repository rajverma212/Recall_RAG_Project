import type {
  AskRequest,
  AskResponse,
  Analytics,
  ChunkingStrategy,
  Document,
  EvaluationDetail,
  EvaluationRun,
  Experiment,
  HealthResponse,
  IngestResponse,
  MetricsResponse,
  PromptVersion,
  ProvidersResponse,
  StreamEvent,
} from './types'

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? 'http://localhost:8000/v1'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`API ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

// ─── Ask ────────────────────────────────────────────────────────────────────

export function ask(body: AskRequest): Promise<AskResponse> {
  return request<AskResponse>('/ask', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function* askStream(body: AskRequest): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${BASE}/ask/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`API ${res.status}: ${text}`)
  }
  const reader = res.body?.getReader()
  if (!reader) throw new Error('No response body')
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const json = line.slice(6).trim()
        if (json) {
          try {
            yield JSON.parse(json) as StreamEvent
          } catch {
            // skip malformed lines
          }
        }
      }
    }
  }
}

// ─── Ingest ─────────────────────────────────────────────────────────────────

export async function ingestDocument(
  file: File,
  strategy: ChunkingStrategy = 'recursive',
): Promise<IngestResponse> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/ingest?strategy=${strategy}`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`API ${res.status}: ${text}`)
  }
  return res.json() as Promise<IngestResponse>
}

// ─── Documents ──────────────────────────────────────────────────────────────

export function listDocuments(): Promise<Document[]> {
  return request<Document[]>('/documents')
}

export function deleteDocument(id: string): Promise<void> {
  return request<void>(`/documents/${id}`, { method: 'DELETE' })
}

// ─── Evaluations ─────────────────────────────────────────────────────────────

export function listEvaluations(): Promise<EvaluationRun[]> {
  return request<EvaluationRun[]>('/evaluations')
}

export function getEvaluation(id: string): Promise<EvaluationDetail> {
  return request<EvaluationDetail>(`/evaluations/${id}`)
}

// ─── Analytics ───────────────────────────────────────────────────────────────

export function getAnalytics(): Promise<Analytics> {
  return request<Analytics>('/analytics')
}

// ─── Experiments ─────────────────────────────────────────────────────────────

export function listExperiments(): Promise<Experiment[]> {
  return request<Experiment[]>('/experiments')
}

export function createExperiment(body: Partial<Experiment>): Promise<Experiment> {
  return request<Experiment>('/experiments', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

// ─── Prompts ─────────────────────────────────────────────────────────────────

export function listPrompts(): Promise<PromptVersion[]> {
  return request<PromptVersion[]>('/prompts')
}

// ─── Providers ───────────────────────────────────────────────────────────────

export function getProviders(): Promise<ProvidersResponse> {
  return request<ProvidersResponse>('/providers')
}

// ─── Health ──────────────────────────────────────────────────────────────────

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health')
}

// ─── Metrics ─────────────────────────────────────────────────────────────────

export function getMetrics(): Promise<MetricsResponse> {
  return request<MetricsResponse>('/metrics')
}
