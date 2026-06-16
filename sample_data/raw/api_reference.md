# Acme DataStream API Reference

## Version 2.5.0 | REST API

Base URL: `https://api.acmecorp.example.com/v2`

Authentication: Bearer token in `Authorization` header.

---

## Authentication

### Obtain Access Token

**POST** `/auth/token`

Request body (JSON):
```json
{
  "client_id": "your_client_id",
  "client_secret": "your_client_secret",
  "grant_type": "client_credentials"
}
```

Response:
```json
{
  "access_token": "eyJhbGc...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

Tokens expire after **3600 seconds (1 hour)**. Clients should refresh tokens proactively before expiry.

**Rate limits**: Authentication endpoint is limited to **10 requests per minute per IP**.

---

## Streams

### List Streams

**GET** `/streams`

Returns all streams owned by or shared with the authenticated user.

Query parameters:
- `page` (integer, default 1)
- `per_page` (integer, default 20, max 100)
- `status` (string): `active` | `paused` | `archived`

Response:
```json
{
  "streams": [
    {
      "id": "stm_abc123",
      "name": "Sales Events",
      "status": "active",
      "created_at": "2025-03-01T12:00:00Z",
      "records_per_second": 450,
      "retention_days": 30
    }
  ],
  "total": 12,
  "page": 1,
  "per_page": 20
}
```

### Create Stream

**POST** `/streams`

```json
{
  "name": "string (required, max 128 chars)",
  "schema": { "field_name": "type", ... },
  "retention_days": 30,
  "compression": "gzip | lz4 | none",
  "partitions": 4
}
```

Default `compression` is `lz4`. Default `partitions` is `4`. Maximum `retention_days` is **365**.

Response: `201 Created` with the full stream object.

### Delete Stream

**DELETE** `/streams/{stream_id}`

Permanently deletes the stream and **all its data**. This action is **irreversible**.

Returns `204 No Content` on success.

---

## Records

### Publish Records

**POST** `/streams/{stream_id}/records`

Send up to **1,000 records per request** (batch limit). Each record must be a JSON object conforming to the stream's schema.

```json
{
  "records": [
    { "user_id": "u_1", "event": "page_view", "ts": 1700000000 },
    { "user_id": "u_2", "event": "purchase",  "ts": 1700000001 }
  ]
}
```

Response: `202 Accepted`
```json
{
  "accepted": 2,
  "rejected": 0,
  "sequence_end": 10042
}
```

**Rate limits for records**: **50,000 records/second** per stream, **10 MB/s** per stream.

### Read Records

**GET** `/streams/{stream_id}/records`

Query parameters:
- `from_sequence` (integer): start sequence number (inclusive)
- `to_sequence` (integer): end sequence number (exclusive)
- `limit` (integer, default 100, max 10000)
- `format`: `json` (default) | `ndjson` | `csv`

---

## Connectors

### Supported Source Connectors

| Connector | Type | Notes |
|-----------|------|-------|
| PostgreSQL | Source | CDC via logical replication |
| MySQL | Source | CDC via binlog |
| S3 | Source/Sink | Batch and streaming modes |
| Kafka | Source/Sink | SASL/SSL supported |
| Snowflake | Sink | Uses COPY INTO |
| BigQuery | Sink | Streaming inserts or batch load |
| Webhook | Source | HMAC-SHA256 signature validation |

### Create Connector

**POST** `/connectors`

```json
{
  "name": "My PG Source",
  "type": "postgresql_source",
  "stream_id": "stm_abc123",
  "config": {
    "host": "db.example.com",
    "port": 5432,
    "database": "mydb",
    "user": "replicator",
    "password": "***",
    "slot_name": "acme_slot",
    "tables": ["public.orders", "public.customers"]
  }
}
```

---

## Transformations

Acme DataStream supports **in-flight transformation pipelines** using SQL-like syntax.

### Create Transformation

**POST** `/streams/{stream_id}/transformations`

```json
{
  "name": "Mask PII",
  "sql": "SELECT user_id, SHA256(email) AS email_hash, event, ts FROM stream",
  "output_stream_id": "stm_xyz789"
}
```

Supported SQL functions: `SHA256`, `MD5`, `UPPER`, `LOWER`, `CAST`, `COALESCE`, `IF`, `CASE`, `DATE_TRUNC`, `EXTRACT`, `REGEXP_REPLACE`.

---

## Error Codes

| HTTP Code | Error Code | Description |
|-----------|------------|-------------|
| 400 | `INVALID_SCHEMA` | Record does not match stream schema |
| 401 | `UNAUTHORIZED` | Missing or expired token |
| 403 | `FORBIDDEN` | Insufficient permissions |
| 404 | `NOT_FOUND` | Resource does not exist |
| 409 | `CONFLICT` | Stream name already exists |
| 422 | `VALIDATION_ERROR` | Request body validation failed |
| 429 | `RATE_LIMITED` | Exceeded rate limit |
| 500 | `INTERNAL_ERROR` | Server error; contact support |
| 503 | `SERVICE_UNAVAILABLE` | Temporary outage; retry with backoff |

**Retry guidance**: For 429 and 503, use **exponential backoff** starting at 1 second, max 32 seconds, with jitter.

---

## Webhooks (Outbound)

Acme DataStream can push events to your HTTPS endpoints.

Events:
- `stream.created`
- `stream.deleted`
- `connector.failed`
- `quota.threshold_reached` (at 80% and 100%)

Webhook payloads are signed with `X-Acme-Signature: sha256=<hmac>`. Validate using your webhook secret.

Retry policy: **5 attempts** with exponential backoff. After 5 failures, the webhook is automatically **suspended**.

---

## Quotas

| Resource | Free Tier | Pro Tier | Enterprise |
|----------|-----------|----------|------------|
| Streams | 3 | 25 | Unlimited |
| Records/month | 1,000,000 | 100,000,000 | Negotiated |
| Retention days | 7 | 90 | 365 |
| Connectors | 2 | 10 | Unlimited |
| Support SLA | Community | 8h business | 1h 24/7 |

---

## SDKs

Official SDKs:
- **Python**: `pip install acme-datastream` (PyPI)
- **Node.js**: `npm install @acmecorp/datastream`
- **Java**: Maven `com.acmecorp:datastream-sdk:2.5.0`
- **Go**: `go get github.com/acmecorp/datastream-go`

All SDKs auto-retry on 429/503, handle token refresh, and support async/await patterns.
