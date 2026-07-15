// ─── Ask / Query ─────────────────────────────────────────────────────────────

export interface Citation {
  marker: number
  chunk_id: string
  document_id: string
  source_file: string
  page_number: number | null
  section_title: string | null
  quote: string | null
  text: string
}

export interface Verification {
  claim: string
  cited_markers: number[]
  status: 'supported' | 'partially_supported' | 'unsupported'
  rationale: string
}

export interface ConfidenceScore {
  retrieval_confidence: number
  reranker_confidence: number
  citation_coverage: number
  citation_accuracy: number
  score: number
}

export interface TraceResult {
  chunk_id: string
  document_id: string
  text: string
  score: number
  source_file: string
  page_number: number | null
  section_title: string | null
  heading_path: string | null
  rank: number
}

export interface TraceStage {
  name: string
  results: TraceResult[]
  elapsed_ms: number
}

export interface Trace {
  dense: TraceStage
  bm25: TraceStage
  rrf: TraceStage
  reranked: TraceStage
}

export interface AskResponse {
  query_id: string
  question: string
  answer: string
  citations: Citation[]
  verifications: Verification[]
  confidence: ConfidenceScore
  trace?: Trace
  cost_usd: number
  latency_ms: number
  prompt_version: string
}

export interface AskRequest {
  question: string
  include_trace?: boolean
  prompt_version?: string
  experiment_id?: string
}

// ─── Streaming ───────────────────────────────────────────────────────────────

export interface StreamTokenEvent {
  type: 'token'
  text: string
}

export interface StreamDoneEvent {
  type: 'done'
  data: AskResponse
}

export type StreamEvent = StreamTokenEvent | StreamDoneEvent

// ─── Ingest ──────────────────────────────────────────────────────────────────

export type ChunkingStrategy = 'fixed' | 'recursive' | 'semantic'

export interface IngestResponse {
  document_id: string
  filename: string
  status: string
  num_chunks: number
  num_duplicates_skipped: number
  message: string
}

// ─── Documents ───────────────────────────────────────────────────────────────

export interface Document {
  id: string
  filename: string
  doc_type: string | null
  title: string | null
  num_pages: number | null
  num_chunks: number
  status: 'processing' | 'ready' | 'error' | string
  chunking_strategy: string | null
  error: string | null
  ingested_at: string
  completed_at: string | null
}

// ─── Evaluations ─────────────────────────────────────────────────────────────

export interface EvaluationRun {
  id: string
  name: string
  dataset: string
  config: Record<string, unknown>
  retrieval_recall: number | null
  answer_correctness: number | null
  faithfulness: number | null
  citation_accuracy: number | null
  confidence_calibration: number | null
  created_at: string
}

export interface ExampleResult {
  example_id: string
  category: string
  question: string
  expected_answer: string
  predicted_answer: string
  metrics: Record<string, number>
  passed: boolean
}

export interface EvaluationDetail {
  run: EvaluationRun
  results: ExampleResult[]
}

export type EvaluationJobStatus = 'idle' | 'running' | 'done' | 'error'

export interface EvaluationJob {
  status: EvaluationJobStatus
  name: string | null
  run_id: string | null
  started_at: string | null
  finished_at: string | null
  error: string | null
}

export interface EvaluationRunRequest {
  name?: string
  strategy?: ChunkingStrategy
  dense_weight?: number
  sparse_weight?: number
}

// ─── Analytics ───────────────────────────────────────────────────────────────

export interface DayCount {
  date: string
  count: number
}

export interface BucketCount {
  bucket: string
  count: number
}

export interface Analytics {
  total_queries: number
  avg_confidence: number
  avg_citation_accuracy: number
  avg_latency_ms: number
  total_cost_usd: number
  queries_by_day: DayCount[]
  confidence_histogram: BucketCount[]
  low_confidence_rate: number
}

// ─── Experiments ─────────────────────────────────────────────────────────────

export interface Experiment {
  id: string
  name: string
  description: string | null
  config: Record<string, unknown>
  evaluation_run_id: string | null
  metrics: Record<string, number> | null
  created_at: string
}

// ─── Prompts ─────────────────────────────────────────────────────────────────

export interface PromptVersion {
  version: string
  name: string
  description: string | null
  is_active: boolean
  system_prompt: string
}

// ─── Providers ───────────────────────────────────────────────────────────────

export interface ProviderStatus {
  healthy: boolean
  state: 'active' | 'fallback'
  detail: string
}

export interface LLMProviderInfo {
  configured: string // the configured provider name (e.g. "anthropic")
  active: string
  model: string
  input_price_per_1m: number
  output_price_per_1m: number
  available: string[]
  keys_present: {
    anthropic: boolean
    openai: boolean
  }
  status: ProviderStatus
}

export interface EmbeddingProviderInfo {
  configured: string
  active: string
  model: string
  dim: number
  available: string[]
  keys_present?: Record<string, boolean>
  status: ProviderStatus
}

export interface ProvidersResponse {
  llm: LLMProviderInfo
  embedding: EmbeddingProviderInfo
}

// ─── Health ──────────────────────────────────────────────────────────────────

export interface HealthCheck {
  ok: boolean
  detail?: string
  // vector_store
  backend?: string
  collection?: string
  vectors?: number | null
  // llm_provider
  configured?: string
  active?: string
  model?: string
  // retrieval
  embedding_provider?: string
}

export interface HealthResponse {
  status: string
  app: string
  version?: string
  environment: string
  checks: Record<string, HealthCheck>
}

// ─── Metrics ─────────────────────────────────────────────────────────────────

export interface StageMetrics {
  count: number
  errors: number
  avg_ms: number
  p95_ms: number
  last_ms: number
}

export interface MetricsResponse {
  uptime_seconds: number
  stages: Record<string, StageMetrics>
  queries: {
    total_queries: number
    avg_latency_ms: number
    success_rate?: number
    citation_accuracy?: number
    avg_confidence: number
    low_confidence_rate: number
  }
}
