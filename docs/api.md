# API Design

The API is served by FastAPI. Interactive documentation is available at `/docs`
and `/redoc`.

In the V9 same-origin demo, the SPA calls relative `/api/...` paths through the
frontend Nginx proxy. Split hosting uses the backend origin configured in
`VITE_API_BASE_URL`.

## Authentication

Protected endpoints require a server-side API key in the `X-API-Key` header.
Missing or invalid credentials return `401` with `error: "unauthorized"`. If
`API_KEY` is not configured, protected endpoints fail closed with `503` and
`error: "authentication_not_configured"`.

Protected endpoints:

- `POST /api/github/repositories/{owner}/{repo}/analysis`
- `GET /api/analyses`
- `GET /api/analyses/{analysis_id}`
- `GET /api/statistics`
- `POST /api/documents`
- `POST /api/documents/{document_id}/extractions`

Public endpoints include `/api/health`, `/api/ready`, `/health`, `/ready`,
`/metrics`, `/docs`, `/redoc`, the root response, and the GitHub read endpoints
listed below. The API key is a single shared secret; it is not a user identity
or tenant boundary.

## Health and readiness

- `GET /api/health` (alias `GET /health`) returns a lightweight liveness response.
  It does not call GitHub or the database.
- `GET /api/ready` (alias `GET /ready`) executes `SELECT 1` against the configured
  database. It returns `200` when the database is reachable and a safe `503`
  (`checks.database = "unavailable"`) when it is not.

## GitHub repository reads

These endpoints are public and call the GitHub REST API:

- `GET /api/github/repositories/{owner}/{repo}`
- `GET /api/github/repositories/{owner}/{repo}/commits`
- `GET /api/github/repositories/{owner}/{repo}/pull-requests`
- `GET /api/github/repositories/{owner}/{repo}/issues`
- `GET /api/github/repositories/{owner}/{repo}/contents`

## Repository analysis and history

### `POST /api/github/repositories/{owner}/{repo}/analysis`

Runs deterministic repository analysis against metadata, recent commits, open
issues, open pull requests, and root contents. The response includes metrics and
findings with severity, category, and evidence. A successful analysis is
persisted to PostgreSQL and is then available through the history and statistics
endpoints. This workflow does not use OpenAI.

### `GET /api/analyses`

Returns persisted analyses newest first. Query parameters are `limit` (default
`20`, range `1`-`100`) and `offset` (default `0`, minimum `0`). The response is
`{ items, total, limit, offset }`.

### `GET /api/analyses/{analysis_id}`

Returns one persisted analysis including metrics and findings, or `404` when it
does not exist.

### `GET /api/statistics`

Returns database aggregates: `total_analyses`, `distinct_owners`,
`distinct_repositories`, `analyses_last_7_days`, `analyses_last_30_days`, and
`latest_analyzed_at` (null when no analyses exist).

## Document workflow (M0-M3)

### `POST /api/documents`

Accepts one multipart `file` field containing a `.txt` or `.md` document encoded
as UTF-8. The document body is validated, stored, and never returned in full.

The `201` response contains `id`, `filename`, `content_type`, `size_bytes`,
`sha256`, `status` (`received`), `received_at`, `updated_at`, and a bounded
`text_preview`. For a document at or below the preview limit, the preview is
empty; longer documents return a strict prefix only.

Default limits are a 1,048,576-byte file, 20,000 text characters, and a 500-
character preview. The whole multipart request is capped at
`DOCUMENT_MAX_SIZE_BYTES + DOCUMENT_MULTIPART_OVERHEAD_BYTES` (1,114,112 bytes by
default). Invalid, empty, non-UTF-8, or unsupported uploads return `422`; an
oversized upload returns `413`.

Intake writes the document and a `document_received` audit event atomically.

### `POST /api/documents/{document_id}/extractions`

Runs the local deterministic extractor against an already-stored document and
stores a new extraction attempt. The response is `201` with `id`, `document_id`,
`provider` (`deterministic`), `model` (`null`), `status` (`succeeded` or
`failed`), `fields`, `warnings`, and `created_at`.

Recognized fields are `client_name`, `total_fee`, `effective_date`, and
`reference_id`. Each field includes `name`, `value`, `confidence`, and optional
`evidence` (`source_quote`, `char_start`, `char_end`, `page`). Offsets are
Unicode code-point offsets and `char_end` is exclusive.

Found values use confidence `0.95`. Missing or ambiguous values are returned as
`null` with confidence `0.0` rather than guessed; ambiguous fields add an
`ambiguous:<field>` warning. A retry is allowed from `received`, `extracted`, or
`extraction_failed`. Documents in `extracting`, `approved`, or `rejected` state
return `409`. An unknown document returns `404`.

If the stored text cannot be read, the attempt is persisted with
`status: "failed"` and warning `document_text_unavailable`; the endpoint still
returns `201`. The claim writes `extraction_started` atomically with the
`extracting` status; finalization writes the extraction attempt, final status,
and success/failure event together in a second transaction.

The extractor treats document content as data, not instructions. It does not
call a model or network service.

## Audit events

The `audit_events` table records document lifecycle events such as
`document_received`, `extraction_started`, `extraction_succeeded`, and
`extraction_failed`. There is currently no audit read API or independent audit
service.

## Not implemented yet

- LLM/OpenAI extraction (M4). `OPENAI_API_KEY` and `OPENAI_MODEL` are reserved
  settings and are not used by the current workflow.
- Document detail, human review/decision, and audit read endpoints.
- Repository connection, incident analysis, and AI chat endpoints.

## Error format

Application errors use a safe JSON body with `detail`, `error`, `message`, and
`retryable` where applicable. Validation errors return `422` with
`error: "invalid_request"`. Database and provider failures return safe `500`,
`502`, or `504` responses without credentials, SQL, document text, or
tracebacks. Rate-limited requests return `429` with `Retry-After`.
