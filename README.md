# AI-Powered Developer Operations Platform

A production-style portfolio project for GitHub repository intelligence, health monitoring, and developer workflow visibility.

## Live Demo

This project is designed for a public portfolio deployment with a React frontend and FastAPI backend.

- Frontend: static SPA served by a host or the same-origin Nginx proxy; the API base is supplied via `VITE_API_BASE_URL` (`/` for same-origin)
- Backend: FastAPI service deployed with `PORT` from the hosting platform
- API docs: generated automatically by FastAPI at `/docs`

## Architecture

- Frontend: React + TypeScript + Vite + Tailwind CSS
- Backend: Python + FastAPI + Pydantic settings
- External integration: GitHub REST API via configurable `GITHUB_API_URL`
- Production hosting pattern: backend on a trusted app platform, frontend on a static site host, or the same-origin Nginx demo
- Local development: Docker Compose for the same-origin frontend proxy, API, and PostgreSQL; Vite-only development is limited to public endpoints

## Local Development

### Backend

The backend persists analyses and documents to PostgreSQL, and the protected
endpoints require `API_KEY`. Set `DATABASE_URL`, run `alembic upgrade head`, and
set `API_KEY` before using the database-backed workflow. Without `API_KEY`, the
protected endpoints fail closed with `503`. For commands run from `backend/`,
either export the variables or copy `.env.example` to `backend/.env`; the
repository-root `.env` is used by Compose.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
API_KEY="$(openssl rand -hex 32)" uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

`npm run dev` starts Vite only. It can call the public health and GitHub read
endpoints, but it does not send `X-API-Key` and has no development proxy. Calls
to analysis creation, analysis history/statistics, document intake, document
reads, extraction, or decisions will return `401` or `503`. Use the Compose/Nginx
workflow below for those protected flows; do not add `API_KEY` to Vite or browser
code. The document workflow is available at `#/documents`, with review at
`#/documents/{id}`.

### Docker Compose

```bash
cp .env.example .env
# Set API_KEY in .env and create secrets/htpasswd as described in V9.
docker compose up --build
```

The frontend proxy is served at `http://localhost:5173` behind owner Basic Auth.
The backend and database publish no host ports. Docker Compose v2.24.0 or newer
is required because the Compose file uses the `env_file` `required:` mapping.
`POSTGRES_PASSWORD` (not `DATABASE_URL` alone) controls the Compose PostgreSQL
password, and PostgreSQL data lives in the named `db_data` volume, so
`docker compose down` keeps it while `docker compose down -v` deletes it (see
[Database data persistence](#database-data-persistence-compose)). The Compose
demo pins the backend to port 8000 (both `PORT` and the legacy `BACKEND_PORT`
alias), matching the backend healthcheck and the Nginx upstream; changing the port
requires updating all of them together.

## Environment Variables

Copy the sample values and adjust for your environment:

```bash
cp .env.example .env
```

Required variables for production deployment:

- `PORT`: platform-provided backend port; the app listens on this value in production
- `APP_ENV=production` and `APP_DEBUG=false`
- `CORS_ALLOWED_ORIGINS`: comma-separated allowed frontend origins for browser access
- `GITHUB_API_URL`: optional override for the GitHub API endpoint; defaults to `https://api.github.com`
- `GITHUB_TOKEN`: optional GitHub token for higher rate limits; keep it out of source control
- `DATABASE_URL`: required for persistence, readiness, and the database-backed endpoints
- `API_KEY`: server-side key required by analysis creation, analysis history/statistics, and document intake/extraction
- `VITE_API_BASE_URL`: frontend build-time API base URL; use `/` for the same-origin Compose/Nginx demo, or the exact backend origin for split hosting
- `BACKEND_UPSTREAM`: frontend Nginx runtime upstream for the V9 same-origin topology; Compose sets `http://backend:8000`, while Render uses the backend's private-network address or public HTTPS origin

For split hosting, set `CORS_ALLOWED_ORIGINS` to the exact frontend origin and
`VITE_API_BASE_URL` to the exact backend origin. The Render hostnames in older
examples are deployment examples, not endpoints verified by this repository;
replace them with your actual service origins. For the V9 same-origin topology,
use `VITE_API_BASE_URL=/` and set `BACKEND_UPSTREAM` on the frontend service to
the backend's private or public Render origin. Keep the backend unexposed where
the platform supports private-only services. See
[docs/development.md](docs/development.md) for the development workflow and
smoke tests.

Never hardcode secrets or tokens in the repository. Keep values in the deployment platform's environment settings. `API_KEY` cannot be placed in a `VITE_*` variable because Vite embeds those values into browser assets.

## Deployment

This project supports two deployment shapes:

1. **Split hosting:** deploy the FastAPI backend to a platform that sets `PORT`
   automatically, configure CORS for the frontend origin, and build the frontend
   with `VITE_API_BASE_URL` set to the backend origin. Protected endpoints require
   a server-side proxy so the browser never holds `API_KEY`.
2. **Same-origin demo (V9):** run the Compose/Nginx topology, which serves the SPA
   and proxies `/api/` with the key added server-side behind owner Basic Auth.
   Build with `VITE_API_BASE_URL=/` and set `BACKEND_UPSTREAM` on the frontend
   service. Compose uses `http://backend:8000`; Render uses the backend's
   private-network address or public HTTPS origin. Keep the backend unexposed
   where the platform supports private-only services.

PostgreSQL and `alembic upgrade head` are required for the database-backed
workflow. Keep the GitHub integration unchanged and rely on the public GitHub
REST API unless a token is provided.

### Recommended production architecture

- Backend: Render or another app platform that supports FastAPI
- Frontend: Cloudflare Pages, Vercel, Netlify, or the V9 same-origin Nginx proxy
- GitHub integration: direct REST API calls with optional token support via environment variables

## API Endpoints

Public endpoints:

- `GET /api/health` (alias `/health`) — backend service liveness
- `GET /api/ready` (alias `/ready`) — database-aware readiness
- `GET /api/github/repositories/{owner}/{repo}` — repository metadata
- `GET /api/github/repositories/{owner}/{repo}/commits` — recent commits
- `GET /api/github/repositories/{owner}/{repo}/pull-requests` — pull requests
- `GET /api/github/repositories/{owner}/{repo}/issues` — repository issues
- `GET /api/github/repositories/{owner}/{repo}/contents` — repository contents

`/metrics`, `/docs`, `/redoc`, and the root response are also public.

Protected endpoints (`X-API-Key`):

- `POST /api/github/repositories/{owner}/{repo}/analysis` — deterministic repository analysis (persists the result)
- `GET /api/analyses` — persisted analysis history (paginated)
- `GET /api/analyses/{analysis_id}` — one persisted analysis
- `GET /api/statistics` — aggregate statistics over persisted analyses
- `POST /api/documents` — document intake (`.txt`/`.md`, UTF-8, multipart `file`)
- `GET /api/documents` — stored documents newest first (paginated)
- `GET /api/documents/{document_id}` — metadata, bounded preview, latest extraction/decision, and recent audit events
- `GET /api/documents/{document_id}/audit` — chronological document audit trail (paginated)
- `POST /api/documents/{document_id}/extractions` — deterministic field extraction
- `POST /api/documents/{document_id}/decisions` — approve or reject the latest successful extraction

Analysis is deterministic and is persisted to PostgreSQL; it does not use OpenAI
and does not claim to be AI-powered. Document extraction is also deterministic:
it recognizes a small set of label lines and returns values, confidence, and
evidence without calling a model or network service. `DATABASE_URL` must point
at PostgreSQL with the Alembic migrations applied. M4/LLM extraction is not
implemented; `OPENAI_API_KEY` and `OPENAI_MODEL` are reserved and currently
unused. See [docs/api.md](docs/api.md) for request and response details.

FastAPI also exposes interactive docs at `/docs` and `/redoc`. The `/metrics`
endpoint is public.

## Testing

```bash
cd backend
pytest
```

```bash
cd frontend
npm run lint
VITE_API_BASE_URL=/ npm run build
npm run verify:dist
```

`verify:dist` checks that the built bundle uses relative API paths and does not
contain an `X-API-Key` reference, a localhost/loopback API URL, or configured
secret values. CI currently runs backend tests plus frontend lint/typecheck and
build; it does not run `verify:dist`.

Current local validation: the backend suite passed with 305 tests and one
Starlette/httpx deprecation warning; frontend lint, production build, and
`verify:dist` passed; and `git diff --check` passed.

## Documentation

- [docs/architecture.md](docs/architecture.md)
- [docs/api.md](docs/api.md)
- [docs/development.md](docs/development.md)
- [docs/security.md](docs/security.md)

## V2 - Infrastructure & DevOps

### Architecture

The React/Vite frontend calls a FastAPI backend, which normalizes data from the configurable GitHub REST API. Docker Compose provides a local backend, frontend, and PostgreSQL service. Since V8, completed analyses are persisted to PostgreSQL and history/statistics are read from it; earlier versions did not use PostgreSQL in request handling.

### Local development

Copy `.env.example` to `.env`, then run `docker compose up --build`. The Compose
stack is the supported local workflow for protected analysis, history, and
document endpoints because the frontend Nginx proxy adds `X-API-Key` server-side
behind owner Basic Auth. The Vite-only frontend can call public endpoints but
cannot call protected endpoints without a server-side proxy; see
[Local Development](#local-development). The local defaults are intentionally
development values.

### Production deployment

No deployment is performed or claimed by this repository. A deployment must provide `PORT`, set `APP_ENV=production` and `APP_DEBUG=false`, configure `CORS_ALLOWED_ORIGINS` with real service origins, and set `VITE_API_BASE_URL` to `/` for the same-origin proxy or to the exact backend origin for split hosting. For the same-origin proxy, also set `BACKEND_UPSTREAM` on the frontend service to the backend's private or public origin; Compose sets `http://backend:8000` locally. Provide secrets through the platform secret store. Do not use the local PostgreSQL password in production.

### Health, readiness, and logging

- `GET /api/health` is a lightweight process health response and does not call GitHub.
- `GET /api/ready` is a database-aware readiness response as of V8. It executes `SELECT 1` and reports PostgreSQL as a live dependency (see [V8 - Database Persistence](#v8---database-persistence)); earlier versions only checked configuration.
- Backend logs use consistent timestamped levels and include method, path, status, and duration. Tokens, authorization headers, and request bodies are not logged.

### Error handling

GitHub timeouts return `504`, rate limits return `429`, authentication failures return `401`, missing resources return `404`, upstream service failures return `502`, and malformed query parameters return `422`. Unexpected failures return a safe `500` message without a stack trace in the response. The frontend consumes the JSON `detail` field when available.

### Docker and CI

The backend container runs Uvicorn on the platform `PORT` as a non-root user. The frontend image builds the static Vite bundle and serves it with Nginx. Compose remains a local development setup and uses an explicitly development-only database default. GitHub Actions runs backend tests plus frontend lint/type validation and a production build on pushes and pull requests; it does not run `verify:dist` and does not deploy.

### Known limitations

PostgreSQL migrations and runtime persistence were not implemented when V2 was written; since V8 they are implemented with Alembic and the `analyses` table, and the document workflow adds the document tables (see [V8 - Database Persistence](#v8---database-persistence) and [Document Intake, Extraction, and Review Reads](#document-intake-extraction-and-review-reads)). GitHub reads are async and use a process-local TTL cache since V4. There is no metrics/tracing platform (only in-process counters). Docker Compose, PostgreSQL migrations, and the local runtime stack have since been verified locally; a clean image rebuild and clean-stack recreation remain unverified.

## V3 - Security & Compliance Hardening

V3 adds environment-validated production CORS, security response headers, configurable process-local rate limiting, bounded and traversal-safe inputs, secret-safe error responses, reusable log redaction, non-root frontend serving, and dependency audit steps in CI. The public health, readiness, metrics, and GitHub read endpoints remain public. Analysis creation, analysis history/statistics, document intake, extraction, document reads, and document decisions require `X-API-Key`; this is a single shared server-side key, not a user system. Browser clients use the same-origin Nginx proxy so the key never enters frontend assets.

See [docs/security.md](docs/security.md) for the threat model, implemented controls, compliance-oriented design, and known limitations. This is security hardening, not a compliance certification or production security audit.

## V4 - Scalability

### Implemented now

- GitHub reads use an async `httpx` client with connection pooling and separate connect/read timeouts configured through environment variables.
- GitHub responses use a bounded, configurable TTL cache. Identical concurrent cache misses are single-flighted within one backend process; errors are never cached.
- Pagination remains bounded, with `GITHUB_MAX_PER_PAGE` controlling the list endpoints.
- The shared GitHub client is closed through FastAPI lifespan handling. Health and readiness do not depend on GitHub availability; readiness additionally verifies database connectivity as of V8.
- The frontend API contract and UI are unchanged. Existing synchronous client doubles remain supported by the service compatibility path.

### Future production scale

The cache and single-flight coordination are process-local, so multiple backend instances can still issue duplicate upstream requests. A distributed cache/lock service, background refresh jobs, metrics, and a production database would be needed for larger deployments. The current application does not claim horizontal scalability has been proven, and repository synchronization/content indexing remain synchronous request candidates for future workers.

## V5 - Robustness & Reliability

V5 adds bounded retries with exponential backoff and jitter for transient read-only GitHub failures, a process-local circuit breaker, structured retryable error metadata while retaining `detail`, request correlation IDs, cache failure isolation, stale-response protection, and contract/regression tests. See [docs/reliability.md](docs/reliability.md) for the failure model and limitations. No production reliability or availability claim is made.

## V6 - Observability

V6 adds JSON-compatible logs, safe `X-Request-ID` correlation, bounded aggregate metrics at `/metrics`, GitHub/cache/retry/circuit instrumentation, and `/health`/`/ready` aliases while preserving the existing `/api/health` and `/api/ready` endpoints. See [docs/observability.md](docs/observability.md). These are locally implemented and CI-validated foundations; no external monitoring or deployment is claimed.

## V7 - Production Deployment Readiness

### Production architecture

The V7 split-hosting pattern deploys two independently managed services: a FastAPI backend container and a static Vite frontend served by the unprivileged Nginx image. The frontend calls the backend origin configured at build time through `VITE_API_BASE_URL`; the backend calls GitHub using server-side configuration and optional `GITHUB_TOKEN`. The V9 section adds a same-origin Nginx proxy alternative for the protected endpoints. PostgreSQL is used at runtime since V8 (the API persists analyses and serves history/statistics) and Compose applies migrations before the API starts; see [V8 - Database Persistence](#v8---database-persistence).

### Required platform settings

For the backend service, set `APP_ENV=production`, `APP_DEBUG=false`, `CORS_ALLOWED_ORIGINS` to the exact HTTPS frontend origin, and allow the hosting platform to provide `PORT`. Set `DATABASE_URL` for the managed PostgreSQL instance. Configure the existing GitHub, timeout, cache, retry, circuit-breaker, rate-limit, and logging variables from `.env.example` as needed. Keep `GITHUB_TOKEN`, database credentials, and other secrets in the platform secret store.

For split hosting, set the frontend build variable `VITE_API_BASE_URL` to the exact public HTTPS backend origin. For the V9 same-origin demo, use the `/` sentinel instead and set the frontend runtime variable `BACKEND_UPSTREAM` to the backend's private-network address or public HTTPS origin so Nginx can proxy `/api/`. No frontend secret belongs in a `VITE_*` variable because Vite embeds those values into browser assets. Production builds fail when this variable is absent; localhost is retained only for local development and Compose defaults.

### Deployment commands and checks

Backend startup command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (the backend Dockerfile already supplies this behavior). Apply the schema with `alembic upgrade head` before the API starts; Compose does this automatically through the one-shot `migrate` service (see [V8 - Database Persistence](#v8---database-persistence)). Frontend startup is the Nginx container command in [frontend/Dockerfile](frontend/Dockerfile). After each service is hosted, verify `GET /health`, `GET /ready`, and `GET /metrics` on the backend, then verify the frontend can load repository data and analysis history through the configured backend origin. Set the final frontend origin in `CORS_ALLOWED_ORIGINS` only after it exists.

### Deployment status and blockers

Deployment is not complete until a public backend host and frontend host are configured and externally verified. This repository does not invent public URLs, provision cloud resources, configure provider credentials, or claim a successful deployment. Docker/PostgreSQL execution has been verified locally, but a clean Docker image rebuild, clean-stack recreation, external DNS, TLS, platform environment settings, CORS from the final browser origin, GitHub access, public frontend/backend communication, and readiness against a managed production database remain deployment-time checks.

## V8 - Database Persistence

V8 adds PostgreSQL-backed persistence for completed repository analyses, Alembic
schema migrations, and a database-aware readiness probe. Analysis stays
deterministic; persistence stores the metrics and findings that were already
computed.

### Persisted data: the `analyses` table

Completed analyses are stored in the `analyses` table:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | integer, primary key | Surrogate identifier, auto-incrementing |
| `owner` | varchar(100), not null, indexed | GitHub repository owner |
| `repository` | varchar(100), not null, indexed | GitHub repository name |
| `analyzed_at` | timestamp with time zone, not null | Time the analysis ran (UTC) |
| `summary` | text, not null | Human-readable analysis summary |
| `metrics` | json, not null | Deterministic metrics captured at analysis time |
| `findings` | json, not null | Findings produced by the deterministic rules |
| `created_at` | timestamp with time zone, not null | Row creation time (`server_default now()`) |

`metrics` and `findings` mirror the analysis response schema, so stored payloads
round-trip without transformation. A successful `POST .../analysis` writes one
row; failed analyses and failed writes write none.

### Alembic migration workflow

Migrations live in `backend/migrations/` and are configured by
`backend/alembic.ini`. The URL is intentionally left blank in `alembic.ini` and
resolved at runtime from the same application settings / `DATABASE_URL`, so
credentials are never committed to the config file. Legacy `postgresql://` and
`postgresql+psycopg2://` URLs are normalized to the installed `psycopg` (v3)
driver.

Run migrations from `backend/` (outside Docker) with:

```bash
cd backend
alembic upgrade head          # apply all migrations
alembic downgrade base        # revert all migrations
alembic check                 # confirm models and migrations agree
alembic upgrade head --sql    # emit offline SQL without connecting
```

### Analysis history, detail, and statistics endpoints

- `GET /api/analyses` — newest-first page of persisted analyses. Query parameters:
  `limit` (integer, default `20`, allowed range `1`–`100`) and `offset` (integer,
  default `0`, minimum `0`). Returns `{ items, total, limit, offset }`, where each
  item contains `id`, `owner`, `repository`, `analyzed_at`, `summary`, and
  `created_at`. Invalid pagination returns `422`.
- `GET /api/analyses/{analysis_id}` — one persisted analysis including `metrics`
  and `findings`; returns `404` when the record does not exist.
- `GET /api/statistics` — database aggregates: `total_analyses`, `distinct_owners`,
  `distinct_repositories`, `analyses_last_7_days`, `analyses_last_30_days`, and
  `latest_analyzed_at` (null when no analyses exist).

Database failures on these endpoints return a safe `500` without SQL text,
credentials, or tracebacks.

### Health versus readiness

- `GET /api/health` (alias `GET /health`) is liveness: it returns service name and
  environment and does not touch the database or GitHub.
- `GET /api/ready` (alias `GET /ready`) is database-aware readiness: it executes
  `SELECT 1` through the configured database session. It returns `200` with
  `checks.database = "ok"` when the database is reachable, and a safe non-2xx
  `503` with `checks.database = "unavailable"` when it is not. No credentials,
  SQL, or tracebacks are exposed.

### Database configuration

Set `DATABASE_URL` to the database service. Use placeholders only:

```bash
DATABASE_URL=postgresql://<user>:<password>@<host>:<port>/<database>
```

Compose uses a `postgres`/`db:5432` URL with an explicitly development-only
default password; production deployments must supply real credentials through the
platform secret store. Never commit real credentials, and never use the local
development password in production.

`POSTGRES_PASSWORD` controls the Compose PostgreSQL password. The `db` service and
both application services derive their connection URL from that value, so changing
`DATABASE_URL` in `.env` alone does not change the Compose database password.

### Database data persistence (Compose)

The Compose `db` service stores PostgreSQL data in the named `db_data` volume,
mounted at `/var/lib/postgresql/data`:

- `docker compose stop` and `docker compose start` keep the containers and data.
- `docker compose down` removes the containers but keeps the named volume, so the
  data is preserved for the next `docker compose up`.
- `docker compose down -v` (or `docker compose down --volumes`) removes the named
  volume and deletes all database data. Treat it as destructive.
- Recreating the `db` container (for example after a Compose change) remounts the
  same named volume, so committed data survives; `docker compose down` is not
  required to pick up configuration changes.

Data-migration note: adding this volume to a stack whose `db` container already
holds unbacked-up data causes Compose to recreate the container. A new empty named
volume is initialized from the image, not from the removed container's writable
layer, so take a `pg_dump` backup (or otherwise preserve the old volume) before
the first `docker compose up` if that data matters.

### Docker Compose migration service and ordering

Compose defines a one-shot `migrate` service that runs `alembic upgrade head`
before the API starts:

- `migrate` waits for `db` to be healthy, applies migrations, then exits
  (`restart: "no"`).
- `backend` waits for `db` (healthy) **and** for `migrate` to complete
  successfully before Uvicorn starts. If the migration fails, the API container
  does not start.
- Migrations therefore run once per deployment rather than in every application
  worker.

Local (non-Compose) backend startup is unchanged: `uvicorn app.main:app --reload`
does not apply migrations automatically, so run `alembic upgrade head` first.

### Verified behavior versus deployment checks

Verified locally in this repository:

- The backend suite passed 305 tests with one Starlette/httpx deprecation
  warning, including analysis persistence and document review coverage.
- Frontend lint, production build, and distribution verification passed.
- `git diff --check` and `docker compose config` passed.
- The local Compose runtime reported healthy PostgreSQL and backend containers;
  the one-shot migration service completed successfully at revision
  `0002_create_documents`; and the backend health endpoint returned HTTP 200.
- Unauthenticated requests to the public frontend and its proxied health
  endpoint returned HTTP 401 as expected under Basic Auth.
- The authenticated browser workflow was exercised for document upload,
  deterministic extraction, approval, rejection with a required reason, and
  persisted audit history.
- Migration tests apply `alembic upgrade head` and downgrade against a temporary
  SQLite database, including preservation of existing analysis rows.

Not yet verified:

- A clean Docker image rebuild.
- A clean-stack recreation with fresh containers and volumes.
- The database-aware readiness probe returning `503` against an unreachable
  PostgreSQL server.
- Container guard fail-fast behavior for missing or unreadable secrets, and
  runtime request-size enforcement.

## Document Intake, Extraction, and Review Reads

The document workflow supports intake, deterministic extraction, and read-only
review. All document endpoints are protected by the same `X-API-Key` boundary as
analysis creation:

- `POST /api/documents` accepts one multipart `file` containing a `.txt` or `.md`
  document encoded as UTF-8. It validates the extension, media type, UTF-8
  decoding, non-empty text, file size, text length, and whole-request size. The
  `201` response returns document metadata and a bounded preview; the stored body
  is never returned in full. Intake writes the document and its
  `document_received` audit event atomically.
- `POST /api/documents/{document_id}/extractions` runs the local deterministic
  extractor and stores a new extraction attempt. It recognizes `client_name`,
  `total_fee`, `effective_date`, and `reference_id`; missing or ambiguous values
  are returned as `null` rather than guessed. The response includes confidence,
  evidence with Unicode offsets, warnings, and `provider: "deterministic"`.
  Extraction records and audit events are committed atomically with the
  document status.
- `GET /api/documents` lists stored documents newest first with bounded
  pagination. `GET /api/documents/{document_id}` returns metadata, a bounded
  preview, the latest extraction and decision, and a bounded recent audit slice.
  `GET /api/documents/{document_id}/audit` returns a chronological page of the
  append-only audit trail. The complete stored body is never returned.
- `POST /api/documents/{document_id}/decisions` approves or rejects the latest
  successful extraction while the document is `extracted`. Rejections require a
  reason. Corrections are recorded on the decision and audit trail without
  changing the original extraction. Decisions are one-time; later attempts
  return `409 document_not_decidable`.

M4/LLM extraction is not implemented: the extractor does not call OpenAI or any
network model, and `OPENAI_API_KEY`/`OPENAI_MODEL` are unused. See
[docs/api.md](docs/api.md) for the field rules and error responses.

## V9 - Single-Owner Public Demo Deployment

The protected endpoints (analysis creation, analysis history/statistics,
document intake, and document extraction) require the server-side `API_KEY` in
`X-API-Key`. A browser cannot hold that key, so the public-demo Compose topology
serves the SPA and proxies the API through a single origin, adding the key
server-side, behind an owner Basic Auth gate.

### Topology

- `frontend` (unprivileged Nginx) is the only published Compose service
  (`5173:8080`). It serves the built SPA at `/` and reverse-proxies `/api/` to
  `BACKEND_UPSTREAM`, injecting `X-API-Key` from the `API_KEY` environment
  variable at container start (rendered into the Nginx config by the image
  entrypoint; never written into frontend assets). Compose sets
  `BACKEND_UPSTREAM=http://backend:8000`; Render sets it to the backend's
  private-network address or public HTTPS origin.
- The entire server, including `/api/`, is protected by Nginx `auth_basic`
  using a single owner credential, so the proxy is not an open relay and the
  protected endpoints are not public.
- `backend` and `db` publish no host ports. The backend is reachable only by the
  frontend proxy over the `edge` network; `db` is reachable only over the
  internal `data` network.
- The SPA is built with `VITE_API_BASE_URL=/`, so it issues relative `/api/...`
  requests to the same origin.

On Render, set `BACKEND_UPSTREAM` on the **frontend** service to the backend's
address shown under **Connect > Internal**, for example
`http://backend-abcd:10000`. Private networking requires the same region and
workspace, and free web services cannot receive private-network traffic. If
private networking is unavailable, use the backend's public HTTPS origin, for
example `https://backend-abcd.onrender.com`. Use an origin with no path, query,
fragment, or trailing slash. Do not change `VITE_API_BASE_URL` from `/` for
this topology.

### Required secrets

- `API_KEY`: the backend API key. Generate with `openssl rand -hex 32`. The
  frontend Nginx entrypoint accepts only `[A-Za-z0-9_-]` with a length of 16-128
  characters because the value is injected into its config. Never put it in
  `VITE_*`, frontend code, browser storage, or responses.
- Owner Basic Auth credential: a single `user:hash` line (the examples use the
  username `owner`). Generate it outside the image and do not commit it. Delivery
  differs by environment:
  - **Compose:** bind-mount the file read-only at
    `/etc/nginx/auth/htpasswd`.
  - **Render:** add a Secret File named `htpasswd`. Render mounts it at
    `/etc/secrets/htpasswd`; the frontend entrypoint creates a symlink at
    `/etc/nginx/auth/htpasswd` only when the bind-mounted path is absent. Render
    exposes Secret Files through group GID 1000, and the image adds the
    unprivileged nginx user (UID 101) to that group. Leave `HTPASSWD_FILE` unset
    on Render; it is a test-only override and does not change the Nginx template
    path.

  The Nginx image does not ship `htpasswd`, so use a host tool:

  ```bash
  mkdir -p secrets
  htpasswd -c -m secrets/htpasswd owner      # prompts for the owner password
  ```

  `-m` writes an apr1 hash that the Alpine Nginx image accepts. `htpasswd -c -B`
  writes bcrypt, which the musl-based image may reject, so prefer `-m`. If
  `htpasswd` is unavailable, use OpenSSL, but note that `openssl passwd` emits the
  hash only; prefix the username yourself to produce the required `user:hash`
  line:

  ```bash
  printf 'owner:%s\n' "$(openssl passwd -apr1 'your-owner-password')" > secrets/htpasswd
  ```

  For the Compose bind mount, the unprivileged Nginx process reads this file as
  UID 101, so its numeric ownership and permissions must allow that user to read
  it. The Compose file documents the supported options: owner UID 101, or group
  GID 0, with mode `640`. Check the numeric ownership with
  `ls -ln secrets/htpasswd`; on a Linux host you can set the documented
  owner/group and mode with:

  ```bash
  sudo chown 101:0 secrets/htpasswd
  chmod 640 secrets/htpasswd
  ```

  Do not use world-writable permissions. Docker Desktop handles bind-mount
  ownership through its file-sharing layer, so confirm the container can read the
  mounted file rather than assuming host numeric IDs map directly. For Render,
  the Secret File mount controls permissions and the image's GID 1000 membership
  supplies read access; no host `chmod` is involved. The entrypoint fails fast if
  the file is unreadable or malformed.

  `secrets/` is gitignored and must stay out of version control. The Render
  Secret File is stored in Render rather than the repository, and
  `frontend/.dockerignore` excludes a build-context file named `htpasswd` so it
  cannot be baked into the image. The frontend container refuses to start
  (fail-fast) when `API_KEY` is missing, unsafe, or out of range, or when the
  htpasswd path is missing, a directory, unreadable, empty, or lacks a
  `user:hash` line.

### Security assumptions

- Serve this only over HTTPS. Basic Auth transmits the owner credential on every
  request; without TLS the credential and session are exposed.
- The backend must not be exposed publicly. Keep it off host ports (as in the
  Compose file) or behind a network that only the frontend can reach; a directly
  reachable backend is still key-protected but becomes an unnecessary exposure.
- The proxy overwrites `X-Forwarded-For`/`X-Real-IP` with the connecting client
  address (it does not append client-supplied values), and the backend honors
  those headers only from the frontend proxy address (`TRUSTED_PROXY_IPS`,
  default `172.28.0.10`, matching the static `FRONTEND_PROXY_IP`). No arbitrary
  client-supplied forwarding header is trusted.
- Basic Auth is a single shared credential: it authenticates "the owner", has no
  per-user identity, MFA, or per-session revocation, and is not rate-limited at
  the edge. This is acceptable for a single-owner demo, not for multi-user use.

### Local development differences

- `docker compose up --build` runs the public-demo topology (proxy + Basic Auth,
  no published backend/db ports, relative API base). Create `secrets/htpasswd`
  and set `API_KEY` in `.env` first. Compose pins the frontend
  `BACKEND_UPSTREAM` to `http://backend:8000`. This is the supported local
  workflow for protected analysis, history, statistics, and document endpoints.
- Backend-only local development is supported: run PostgreSQL, apply
  `alembic upgrade head`, set `API_KEY`, start `uvicorn app.main:app --reload`,
  and call protected endpoints with `curl -H "X-API-Key: $API_KEY"`. Public
  health and GitHub read endpoints do not require the header.
- Vite-only local development (`npm run dev` with `VITE_API_BASE_URL` pointing
  at `http://localhost:8000`) cannot call protected endpoints: the browser does
  not send `X-API-Key` and there is no Vite development proxy. Use the Compose/
  Nginx workflow or another server-side proxy for those flows. Do not embed the
  key in Vite or browser code.
- Split hosting (static frontend + separate backend, as in V7) is still
  supported: set `VITE_API_BASE_URL` to the absolute backend origin and keep the
  key server-side; browser clients then need a server-side proxy or owner gate
  for the protected endpoints.

### Verification

- Backend: `cd backend && pytest`.
- Frontend: `cd frontend && npm run lint && VITE_API_BASE_URL=/ npm run build
  && npm run verify:dist`. The last step fails if the bundle contains an
  `X-API-Key` reference, a localhost/loopback API URL, or any configured secret
  value, and succeeds only when relative `/api/...` paths are present.

### Container verification status

Local Compose runtime checks passed: `docker compose config` succeeded; the
PostgreSQL and backend containers reported healthy; the one-shot migration
service completed at revision `0002_create_documents`; the backend health
endpoint returned HTTP 200; unauthenticated requests to the frontend and its
proxied health endpoint returned HTTP 401 as expected; and the authenticated
browser workflow completed upload, deterministic extraction, approval, rejection
with a required reason, and persisted audit history. The runtime behavior
confirms that the image rendered
`/etc/nginx/templates/default.conf.template` into
`/etc/nginx/conf.d/default.conf` and that `auth_basic` gates both the SPA and
`/api/`.

Not yet verified: clean-stack recreation with fresh containers and volumes, a
full Compose rebuild/runtime pass after the Render Secret File change, and
runtime request-size enforcement. The frontend image was rebuilt locally for
this fix; the guard's missing-secret fail-closed path, the GID 1000 startup
symlink bridge, and the unprivileged Nginx group membership were exercised in
that image. The image family was confirmed (from the upstream
`nginx`/`nginx-unprivileged` Dockerfiles) to install `envsubst`, ship
`/docker-entrypoint.d/20-envsubst-on-templates.sh`, keep the entrypoint, and own
`/etc/nginx` as the unprivileged user.
