# Acme Corp Engineering Standards

## Version 1.8 | Engineering Leadership | 2026

---

## 1. Coding Standards

### Python

- Use **Python 3.11+** for all new projects. Python 3.9 is the minimum for maintained projects.
- Follow **PEP 8** with a line length of **100 characters** (enforced via `ruff`).
- Type annotations are **required** for all public functions and class attributes.
- Docstrings: Google-style for all public functions, classes, and modules.
- Testing: **pytest** is the standard. Minimum coverage is **80%** for new code. Coverage measured via `pytest-cov`.
- Dependency management: **uv** for new projects; `pip` + `requirements.txt` acceptable for legacy.

### TypeScript / JavaScript

- **TypeScript** is required for all new frontend and Node.js backend projects.
- `strict` mode enabled in `tsconfig.json`.
- Formatting: **Prettier** with default config (80-char line width, single quotes).
- Linting: **ESLint** with `@typescript-eslint/recommended` and `acme/recommended` shared config.
- Testing: **Vitest** for unit tests; **Playwright** for E2E tests.

### Go

- Follow the official **Effective Go** guidelines.
- Use `gofmt` and `golangci-lint`.
- Error handling: always wrap errors with `fmt.Errorf("...: %w", err)`.

---

## 2. Git Workflow

### Branch Naming Convention

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feature/<ticket>-<short-desc>` | `feature/ACM-1234-add-stream-pagination` |
| Bug fix | `fix/<ticket>-<short-desc>` | `fix/ACM-5678-null-pointer-on-empty-schema` |
| Hotfix | `hotfix/<ticket>-<short-desc>` | `hotfix/ACM-9999-cert-renewal` |
| Chore | `chore/<desc>` | `chore/update-dependencies-jan-2026` |

### Commit Messages

Use **Conventional Commits** format:
```
<type>(<scope>): <subject>

[body]

[footer]
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`

Example:
```
feat(streams): add pagination to list-streams endpoint

Adds cursor-based pagination using sequence IDs. Fixes performance
issues on accounts with 1000+ streams.

Closes: ACM-1234
```

### Pull Request Requirements

1. PR title must follow Conventional Commits format.
2. PR description must include: "What", "Why", "Testing done", and "Screenshots/recordings" (if UI change).
3. Minimum **1 approving review** required (2 for changes to `main`-branch-protected paths: `app/core/`, `app/db/`, `app/models/`).
4. All CI checks must pass before merge:
   - Lint
   - Type check
   - Unit tests
   - Integration tests
   - Security scan (Snyk, Trivy for Docker images)
5. Merge strategy: **Squash and merge** for feature branches; **Merge commit** for release branches.

---

## 3. API Design Standards

### RESTful APIs

- Use **REST** for synchronous request/response APIs.
- Use **WebSockets or Server-Sent Events** for real-time/streaming APIs.
- API versioning: **URL prefix versioning** (`/v1/`, `/v2/`). Maintain backward compatibility within a version for at least **12 months** before deprecation.

### Naming Conventions

- URLs: `kebab-case` (e.g., `/stream-groups/`, not `/streamGroups/`).
- JSON fields: `snake_case`.
- HTTP methods follow standard semantics (GET = read-only, POST = create, PUT = full replace, PATCH = partial update, DELETE = remove).

### Pagination

All list endpoints must be paginated. Use **cursor-based pagination** for large or frequently-updated collections; offset pagination is acceptable for collections under 10,000 items.

Response envelope for paginated lists:
```json
{
  "items": [...],
  "total": 100,
  "next_cursor": "opaque_token",
  "has_more": true
}
```

### Error Responses

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable description",
    "details": [
      { "field": "name", "issue": "must be unique" }
    ],
    "request_id": "req_abc123"
  }
}
```

Always return a `request_id` for traceability.

---

## 4. Testing Standards

### Test Pyramid

Target distribution:
- **Unit tests**: 70% of all tests. Fast, isolated, no external dependencies.
- **Integration tests**: 25%. Test service interactions, database queries, external APIs (using testcontainers or mocks).
- **E2E tests**: 5%. Full user flows in a staging environment.

### Test Naming

```python
def test_<unit_under_test>_<state_or_input>_<expected_behavior>():
```

Example: `test_create_stream_with_duplicate_name_returns_409()`

### Database Tests

- Use **pytest-postgresql** for PostgreSQL tests (isolated ephemeral DB per test session).
- Use **factory_boy** for test data fixtures.
- Never write tests that depend on production data.

---

## 5. Observability Standards

All production services must emit:

### Metrics
- **Request rate** (requests/second)
- **Error rate** (4xx, 5xx separately)
- **Latency** (P50, P95, P99)
- **Saturation** (CPU, memory, queue depth)

Use the `acme-metrics` Python library which wraps Prometheus client. Metrics must be labelled with `service`, `env`, and `version`.

### Logging

- Structured logs (JSON) only in production.
- Log levels: DEBUG (dev only), INFO (request lifecycle), WARNING (degraded), ERROR (failures).
- Never log sensitive data (passwords, API keys, PII). Use `acme-logger` which has auto-redaction for common patterns.
- Correlation ID (`request_id`) must appear in every log line within a request context.

### Tracing

- **OpenTelemetry** with Jaeger backend.
- Instrument all database queries, outbound HTTP calls, and queue publishes.
- Trace sampling rate: **1% in production**, 100% in staging.

---

## 6. Security Standards in Code

- **Never hardcode secrets.** Use environment variables; in production, secrets are injected via Kubernetes Secrets sourced from HashiCorp Vault.
- **SQL injection prevention**: Use parameterized queries (ORM or raw). Never concatenate user input into SQL strings.
- **Input validation**: Validate all external inputs at the API boundary (Pydantic for Python; Zod for TypeScript).
- **Dependencies**: Run `snyk test` before merging. Any HIGH or CRITICAL vulnerability blocks merge.
- **CORS**: Whitelist specific origins only; never use `*` in production.
- **HTTP security headers**: Enforce via Cloudflare + nginx: `Strict-Transport-Security`, `Content-Security-Policy`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`.

---

## 7. Code Review Guidelines

### Reviewer Responsibilities
- Review within **1 business day** of being assigned.
- Focus on correctness, security, maintainability, and adherence to standards—not style (leave that to linters).
- Use PR comment categories: `[blocker]` (must fix), `[suggestion]` (nice-to-have), `[question]` (clarification needed), `[nit]` (minor style, non-blocking).

### Author Responsibilities
- Keep PRs small: **< 400 lines changed** is the target. Larger PRs need explicit justification.
- Respond to all review comments within 1 business day.
- Do not merge your own PR (exception: solo hotfixes with SRE Lead approval during incidents).

---

## 8. Infrastructure as Code (IaC)

- **Terraform** for all cloud infrastructure. No manual console changes in production.
- Modules live in `github.com/acmecorp/terraform-modules`.
- All Terraform plans must be reviewed before `apply`.
- Resource naming convention: `acme-<env>-<service>-<resource>` (e.g., `acme-prod-api-rds`).

---

*Questions? #engineering-standards on Slack or open an issue in the `acmecorp/engineering-docs` GitHub repo.*
