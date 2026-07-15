# Acme DataStream Architecture Overview

## Version 2.3 | Platform Engineering | 2026

---

## System Overview

Acme DataStream is a managed, cloud-native real-time data streaming platform. The system processes and delivers event streams from producers to consumers with sub-second latency and at-least-once delivery guarantees (exactly-once available on Enterprise).

---

## High-Level Architecture

```
Producers → [API Gateway / WAF (Cloudflare)] → [Load Balancer (AWS ALB)]
           ↓
      [API Service (FastAPI, Python)]
           ↓
      [Apache Kafka] → [Ingest Workers (Python)] → [PostgreSQL (metadata)]
                                                  → [Qdrant (vectors)]
                                                  → [S3 (raw storage)]
           ↓
      [Stream Router] → [Consumer WebSocket Service]
                     → [Connector Workers] → [Sinks: Snowflake, BigQuery, S3, ...]
```

---

## Component Details

### 1. API Gateway Layer

- **Provider**: Cloudflare (WAF, DDoS protection, TLS termination, CDN for static assets).
- **Load Balancer**: AWS ALB with HTTP/2 support.
- **Rate Limiting**: Applied at Cloudflare (coarse) and API service (per-account).

### 2. API Service

- **Framework**: FastAPI (Python 3.11+) with Uvicorn (ASGI).
- **Deployment**: Kubernetes (AWS EKS), 4–16 replicas depending on load.
- **Authentication**: JWT validation against Okta.
- **Schema validation**: Pydantic v2.
- **Health endpoint**: `/healthz` (liveness), `/readyz` (readiness).

### 3. Message Broker — Apache Kafka

- **Cluster**: 6-broker cluster across 3 Availability Zones (US-East).
- **Replication factor**: 3 for all topics.
- **Retention**: 7 days by default; configurable per-topic up to stream's `retention_days`.
- **Kafka version**: 3.7.0.
- **Compaction**: Log compaction enabled on the `_offsets` and `_schemas` topics only.
- **Throughput**: Designed for 200,000+ records/second sustained.

### 4. Ingest Workers

- **Language**: Python 3.11.
- **Concurrency model**: asyncio with `aiokafka` consumer.
- **Responsibilities**: Schema validation, PII tokenization (optional), deduplication, write to PostgreSQL (metadata), Qdrant (search index), S3 (raw archive).
- **Scaling**: Kubernetes HPA based on Kafka consumer group lag.

### 5. Metadata Store — PostgreSQL

- **Version**: PostgreSQL 16.
- **Deployment**: AWS RDS Multi-AZ.
- **Instance type**: `db.r6g.2xlarge` (8 vCPU, 64 GB RAM) in production.
- **Extensions used**: `pg_stat_statements`, `pgcrypto`, `uuid-ossp`.
- **Connection pooling**: PgBouncer (transaction mode, max 500 connections).

### 6. Vector Store — Qdrant

- **Purpose**: Semantic search on stream records and documentation.
- **Deployment**: 2-node Qdrant cluster on `r6g.2xlarge` instances.
- **Collection**: `rag_chunks` — 1536-dimensional vectors (OpenAI `text-embedding-3-small` or offline fallback).
- **Distance metric**: Cosine similarity.

### 7. Object Storage — AWS S3

- **Buckets**:
  - `acme-prod-raw`: Raw ingest archives. Lifecycle rule: Glacier after 90 days.
  - `acme-prod-processed`: Processed chunk metadata.
  - `acme-prod-backups`: Database backups and Qdrant snapshots.
  - `acme-prod-connector-staging`: Temporary storage for batch sink operations.
- **Encryption**: SSE-S3 for all buckets; SSE-KMS for backups bucket.

### 8. Stream Router

- Routes processed records to subscribed consumers via WebSocket connections.
- Maintains a connection registry in Redis (Cluster mode, 6 nodes).
- Heartbeat every 30 seconds; connection timeout after 60 seconds without heartbeat.

### 9. Connector Workers

- Each connector type has a dedicated worker pool.
- Sinks: Snowflake (COPY INTO), BigQuery (streaming inserts), S3 (Parquet batches), Kafka (mirror-maker pattern).
- Sources: PostgreSQL (logical replication / pgoutput), MySQL (binlog via Debezium), Webhook (HMAC-validated HTTP).

---

## Data Flow: Record Publish

1. Producer sends HTTP POST to `/v2/streams/{stream_id}/records`.
2. API Service validates authentication, authorization, rate limits, and schema.
3. API Service publishes to Kafka topic `streams.{stream_id}.raw`.
4. API Service responds `202 Accepted` to producer (non-blocking).
5. Ingest Worker consumes from Kafka, applies transformations, deduplication.
6. Ingest Worker writes:
   - Record metadata to PostgreSQL.
   - Embedding vector to Qdrant (if semantic indexing enabled).
   - Raw bytes to S3 with lifecycle management.
7. Stream Router reads from `streams.{stream_id}.processed` and pushes to WebSocket consumers.
8. Connector Workers read from `streams.{stream_id}.processed` and write to configured sinks.

End-to-end latency target: **P99 < 500ms** from producer POST to consumer delivery.

---

## Deployment: Kubernetes

- **EKS version**: 1.30.
- **Node groups**:
  - `api`: `c6g.xlarge` (4 vCPU, 8 GB). Spot instances with on-demand fallback.
  - `kafka`: `r6g.2xlarge` (8 vCPU, 64 GB). On-demand only.
  - `workers`: `c6g.2xlarge` (8 vCPU, 16 GB). Spot instances.
  - `qdrant`: `r6g.2xlarge`. On-demand only.
- **GitOps**: Argo CD with automated sync from the `main` branch to staging; manual promotion to production.
- **Service mesh**: Istio (mTLS between all services in production).

---

## Reliability Architecture

### Availability Targets
- API service: **99.95%** (designed; actual SLO 99.9%).
- Kafka: 99.99% (multi-AZ, RF=3).
- PostgreSQL: 99.99% (RDS Multi-AZ automatic failover within 60 seconds).

### Circuit Breakers
- All outbound calls from API service use circuit breakers (via `tenacity` + custom CB logic).
- Fallback: In-memory queue when Kafka is unavailable (up to 10,000 records per pod).

### Chaos Engineering
- Monthly **GameDay** exercises using AWS Fault Injection Simulator.
- Automated chaos tests in staging via **Chaos Mesh** (random pod kills, network partition, latency injection).

---

## Security Architecture

- **Zero-trust network**: No implicit trust between services; all inter-service calls use mTLS (Istio).
- **Secrets**: HashiCorp Vault (injected as environment variables via Vault Agent sidecar).
- **RBAC**: Kubernetes RBAC with principle of least privilege.
- **Image security**: Trivy scan on all container images in CI; only signed images deployed (cosign / Sigstore).
- **Audit logging**: All API calls logged to Loki with 1-year retention.

---

## Observability Stack

| Tool | Purpose |
|------|---------|
| Prometheus | Metrics collection |
| Grafana | Dashboards and alerting |
| Loki | Log aggregation |
| Tempo | Distributed tracing (OpenTelemetry) |
| Checkly | Synthetic monitoring |
| PagerDuty | Incident alerting and escalation |

---

## Disaster Recovery

- **DR region**: US-West-2 (warm standby, promoted within 4 hours for PostgreSQL, 30 minutes for API layer).
- **Kafka DR**: MirrorMaker 2 replicates all topics to US-West-2 cluster with lag < 5 minutes.
- **RTO**: 4 hours (full region failover).
- **RPO**: 1 hour.

---

*Maintained by Platform Engineering. Last major revision: Q1 2026. For questions, open an issue in `acmecorp/platform-docs` or Slack #platform-eng.*
