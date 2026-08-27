# AI-Powered Developer Operations Platform

A production-style portfolio project for GitHub repository intelligence, health monitoring, and developer workflow visibility.

## Live Demo

This project is designed for a public portfolio deployment with a React frontend and FastAPI backend.

- Frontend: deployed behind a production host with the backend URL supplied via `VITE_API_BASE_URL`
- Backend: FastAPI service deployed with `PORT` from the hosting platform
- API docs: generated automatically by FastAPI at `/docs`

## Architecture

- Frontend: React + TypeScript + Vite + Tailwind CSS
- Backend: Python + FastAPI + Pydantic settings
- External integration: GitHub REST API via configurable `GITHUB_API_URL`
- Production hosting pattern: backend on a trusted app platform, frontend on a static site host
- Local development: Docker Compose for the API service and local Vite frontend

## Local Development

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Docker Compose

```bash
docker compose up --build
```

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
- `DATABASE_URL`: required when the app is connected to Postgres
- `VITE_API_BASE_URL`: frontend API base URL used for deployed backend requests

For the current Render services, set `CORS_ALLOWED_ORIGINS` to exactly
`https://ai-powered-developer-operations-platform.onrender.com` and set the
frontend build variable `VITE_API_BASE_URL` to exactly
`https://ai-powered-developer-operations-backend.onrender.com`. See
[docs/development.md](docs/development.md) for service roots and smoke tests.

Never hardcode secrets or tokens in the repository. Keep values in the deployment platform's environment settings.

## Deployment

This project is intentionally structured for a simple deployment flow:

1. Deploy the FastAPI backend to a platform that sets `PORT` automatically.
2. Configure allowed CORS origins for the deployed frontend URL.
3. Set `VITE_API_BASE_URL` to the deployed backend URL in the frontend build environment.
4. Keep the GitHub integration unchanged and rely on the public GitHub REST API unless a token is provided.

### Recommended production architecture

- Backend: Render or another app platform that supports FastAPI
- Frontend: Cloudflare Pages, Vercel, or Netlify for the static React build
- GitHub integration: direct REST API calls with optional token support via environment variables

## API Endpoints

Core endpoints:

- `GET /api/health` — backend service health check
- `GET /api/github/repositories/{owner}/{repo}` — repository metadata
- `GET /api/github/repositories/{owner}/{repo}/commits` — recent commits
- `GET /api/github/repositories/{owner}/{repo}/pull-requests` — pull requests
- `GET /api/github/repositories/{owner}/{repo}/issues` — repository issues
- `GET /api/github/repositories/{owner}/{repo}/contents` — repository contents
- `POST /api/github/repositories/{owner}/{repo}/analysis` — deterministic V1 repository analysis

V1 analysis uses the existing GitHub REST integration to calculate repository
activity and maintenance indicators. It does not require OpenAI, does not claim
to be AI-powered, and does not persist results. PostgreSQL is not used during
request handling; `OPENAI_API_KEY` and `DATABASE_URL` remain optional settings.

FastAPI also exposes interactive docs at `/docs` and `/redoc`.

## Testing

```bash
cd backend
pytest
```

```bash
cd frontend
npm run build
```

## Documentation

- [docs/architecture.md](docs/architecture.md)
- [docs/api.md](docs/api.md)
- [docs/development.md](docs/development.md)

## V2 - Infrastructure & DevOps

### Architecture

The React/Vite frontend calls a FastAPI backend, which normalizes data from the configurable GitHub REST API. Docker Compose provides a local backend, frontend, and PostgreSQL service; the current API does not yet use PostgreSQL in request handling.

### Local development

Copy `.env.example` to `.env`, then run `docker compose up --build`, or start the backend and frontend separately using the commands above. The local defaults are intentionally development values.

### Production deployment

No deployment is performed or claimed by this repository. A deployment must provide `PORT`, set `APP_ENV=production` and `APP_DEBUG=false`, configure `CORS_ALLOWED_ORIGINS` and `VITE_API_BASE_URL` with real service origins, and provide secrets through the platform secret store. Do not use the local PostgreSQL password in production.

### Health, readiness, and logging

- `GET /api/health` is a lightweight process health response and does not call GitHub.
- `GET /api/ready` is a deterministic configuration-readiness response. PostgreSQL is not reported as a live dependency because the current API does not access it.
- Backend logs use consistent timestamped levels and include method, path, status, and duration. Tokens, authorization headers, and request bodies are not logged.

### Error handling

GitHub timeouts return `504`, rate limits return `429`, authentication failures return `401`, missing resources return `404`, upstream service failures return `502`, and malformed query parameters return `422`. Unexpected failures return a safe `500` message without a stack trace in the response. The frontend consumes the JSON `detail` field when available.

### Docker and CI

The backend container runs Uvicorn on the platform `PORT` as a non-root user. The frontend image builds the static Vite bundle and serves it with Nginx. Compose remains a local development setup and uses an explicitly development-only database default. GitHub Actions runs backend tests plus frontend lint/type validation and a production build on pushes and pull requests; it does not deploy.

### Known limitations

PostgreSQL migrations and runtime persistence are not implemented, GitHub calls are synchronous and uncached, there is no metrics/tracing platform, and Docker/CI execution has not been verified in this environment where Docker is unavailable.

## V3 - Security & Compliance Hardening

V3 adds environment-validated production CORS, security response headers, configurable process-local rate limiting, bounded and traversal-safe inputs, secret-safe error responses, reusable log redaction, non-root frontend serving, and dependency audit steps in CI. Current read-only endpoints remain public; authentication is intentionally a future boundary rather than an invented user system.

See [docs/security.md](docs/security.md) for the threat model, implemented controls, compliance-oriented design, and known limitations. This is security hardening, not a compliance certification or production security audit.

## V4 - Scalability

### Implemented now

- GitHub reads use an async `httpx` client with connection pooling and separate connect/read timeouts configured through environment variables.
- GitHub responses use a bounded, configurable TTL cache. Identical concurrent cache misses are single-flighted within one backend process; errors are never cached.
- Pagination remains bounded, with `GITHUB_MAX_PER_PAGE` controlling the list endpoints.
- The shared GitHub client is closed through FastAPI lifespan handling. Health and readiness remain lightweight and do not depend on GitHub availability.
- The frontend API contract and UI are unchanged. Existing synchronous client doubles remain supported by the service compatibility path.

### Future production scale

The cache and single-flight coordination are process-local, so multiple backend instances can still issue duplicate upstream requests. A distributed cache/lock service, background refresh jobs, metrics, and a production database would be needed for larger deployments. The current application does not claim horizontal scalability has been proven, and repository synchronization/content indexing remain synchronous request candidates for future workers.

## V5 - Robustness & Reliability

V5 adds bounded retries with exponential backoff and jitter for transient read-only GitHub failures, a process-local circuit breaker, structured retryable error metadata while retaining `detail`, request correlation IDs, cache failure isolation, stale-response protection, and contract/regression tests. See [docs/reliability.md](docs/reliability.md) for the failure model and limitations. No production reliability or availability claim is made.

## V6 - Observability

V6 adds JSON-compatible logs, safe `X-Request-ID` correlation, bounded aggregate metrics at `/metrics`, GitHub/cache/retry/circuit instrumentation, and `/health`/`/ready` aliases while preserving the existing `/api/health` and `/api/ready` endpoints. See [docs/observability.md](docs/observability.md). These are locally implemented and CI-validated foundations; no external monitoring or deployment is claimed.

## V7 - Production Deployment Readiness

### Production architecture

Deploy two independently managed services: a FastAPI backend container and a static Vite frontend served by the unprivileged Nginx image. The frontend calls the backend origin configured at build time through `VITE_API_BASE_URL`; the backend calls GitHub using server-side configuration and optional `GITHUB_TOKEN`. PostgreSQL remains a local Compose dependency only and is not used by current request handling.

### Required platform settings

For the backend service, set `APP_ENV=production`, `APP_DEBUG=false`, `CORS_ALLOWED_ORIGINS` to the exact HTTPS frontend origin, and allow the hosting platform to provide `PORT`. Configure the existing GitHub, timeout, cache, retry, circuit-breaker, rate-limit, and logging variables from `.env.example` as needed. Keep `GITHUB_TOKEN`, database credentials, and other secrets in the platform secret store.

For the frontend service, set the build variable `VITE_API_BASE_URL` to the exact public HTTPS backend origin. No frontend secret belongs in a `VITE_*` variable because Vite embeds those values into browser assets. Production builds fail when this variable is absent; localhost is retained only for local development and Compose defaults.

### Deployment commands and checks

Backend startup command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (the backend Dockerfile already supplies this behavior). Frontend startup is the Nginx container command in [frontend/Dockerfile](frontend/Dockerfile). After each service is hosted, verify `GET /health`, `GET /ready`, and `GET /metrics` on the backend, then verify the frontend can load repository data through the configured backend origin. Set the final frontend origin in `CORS_ALLOWED_ORIGINS` only after it exists.

### Deployment status and blockers

Deployment is not complete until a public backend host and frontend host are configured and externally verified. This repository does not invent public URLs, provision cloud resources, configure provider credentials, or claim a successful deployment. Docker was unavailable during local validation, and external DNS, TLS, platform environment settings, CORS from the final browser origin, GitHub access, and public frontend/backend communication remain deployment-time checks.
