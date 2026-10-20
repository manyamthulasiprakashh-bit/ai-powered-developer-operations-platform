# Development Guide

## Prerequisites

- Python 3.12 and the backend dependencies in `backend/requirements.txt`
- Node.js 20 or newer and the frontend dependencies in `frontend/package.json`
- PostgreSQL for persistence, readiness, analysis history/statistics, and the
  document workflow
- Docker Compose v2.24.0 or newer for the same-origin proxy/Basic Auth workflow
  (the Compose file uses the `env_file` `required:` mapping)

Copy `.env.example` to `.env` and adjust values: use the repository root for
Compose, or `backend/.env` for Uvicorn/Alembic commands run from `backend/`.
Do not commit `.env`, `secrets/`, API keys, tokens, or database passwords.

## Recommended local workflow: Compose + Nginx

The supported local workflow for protected endpoints is the same-origin Compose
stack. It serves the SPA and proxies `/api/` through Nginx, adding `X-API-Key`
server-side behind owner Basic Auth.

```bash
cp .env.example .env
# Set a long random API_KEY in .env.
mkdir -p secrets
htpasswd -c -m secrets/htpasswd owner      # prompts; writes owner:apr1-hash
# OpenSSL alternative (emits the hash only, so prefix the username):
# printf 'owner:%s\n' "$(openssl passwd -apr1 'your-owner-password')" > secrets/htpasswd

docker compose up --build
```

The Nginx process reads `secrets/htpasswd` as UID 101, so make the file readable
by that numeric user and do not use world-writable permissions. See
[Required secrets](../README.md#required-secrets) for the supported owner/group
and `640` mode settings, including the Docker Desktop ownership caveat.

Open `http://localhost:5173` and authenticate with the owner credential. The
`migrate` service applies Alembic migrations before the API starts. The backend
and database do not publish host ports.

## Backend-only local development

1. Start PostgreSQL and set `DATABASE_URL`.
2. Apply the schema: `cd backend && alembic upgrade head`.
3. Set `API_KEY` to a long random value.
4. Start `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`.

Public health and GitHub read endpoints work without a key. Protected endpoints
require the header:

```bash
curl -i http://localhost:8000/api/health
curl -i -H "X-API-Key: $API_KEY" http://localhost:8000/api/statistics
```

Analysis creation, history/statistics, document intake, and document extraction
all use PostgreSQL. Without a reachable database, database-backed endpoints
return safe `500` responses and `/api/ready` reports the database as unavailable.

## Vite-only local development

`npm run dev` starts Vite only. With no `VITE_API_BASE_URL` (or a value pointing
at `http://localhost:8000`), the SPA can call public health and GitHub read
endpoints. It cannot call protected endpoints: the browser does not send
`X-API-Key`, and this repository does not include a Vite development proxy.
Calls to analysis creation, analysis history/statistics, document intake, or
document extraction will return `401` (or `503` when `API_KEY` is unset).

For those flows, use the Compose/Nginx workflow, a backend-only curl workflow, or
another server-side proxy. Never put `API_KEY` in a `VITE_*` variable, browser
storage, or frontend source; Vite embeds `VITE_*` values into browser assets.

## Running tests and checks

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

The backend suite uses in-memory SQLite. It does not verify a live PostgreSQL
server, Docker, or Nginx runtime behavior.

## Docker

```bash
docker compose up --build
```

Docker Compose v2.24.0 or newer is required. The Compose demo pins the backend to
port 8000: the backend healthcheck and the frontend `BACKEND_UPSTREAM` both target
8000. Compose sets both `PORT` and the legacy `BACKEND_PORT` alias (accepted by
`backend/app/core/config.py`) to `8000` so a stray `.env` value cannot move the
backend, and pins the frontend `BACKEND_UPSTREAM` to
`http://backend:8000`. Changing the port means updating both variables, the
healthcheck URL, and `BACKEND_UPSTREAM` together. Platform (non-Compose)
deployments still use the platform-provided `PORT` and must set
`BACKEND_UPSTREAM` on the frontend service.

PostgreSQL data is stored in the named `db_data` volume: `docker compose down`
removes the containers but preserves the volume and its data, while
`docker compose down -v` deletes the volume and all database data.
`POSTGRES_PASSWORD` controls the Compose database password; the Compose services
build their connection URL from it, so changing `DATABASE_URL` in `.env` alone
does not change the Compose database password.

`docker compose config` and the full stack require Docker, which was unavailable
during this checkpoint's validation. The Nginx template rendering, Basic Auth
gate, request-size enforcement, guard failure behavior, and migration ordering
against real PostgreSQL remain deployment-time checks.

## Deployment example and status

This repository does not contain a Render manifest and does not record a
verified public deployment. The placeholders below are examples, not endpoints
verified by this repository. Replace them with the actual origins from your
provider after deployment.

If you configure two Render services from the repository root:

| Service | Root directory | Dockerfile | Runtime/build behavior |
| --- | --- | --- | --- |
| Backend | `backend` | `Dockerfile` | The image starts Uvicorn on Render's `PORT`. |
| Frontend | `frontend` | `Dockerfile` | The image runs `npm run build`, then serves `dist` with Nginx. |

Backend environment variables:

```text
APP_ENV=production
APP_DEBUG=false
CORS_ALLOWED_ORIGINS=https://<frontend-host>
DATABASE_URL=postgresql://<user>:<password>@<host>:<port>/<database>
API_KEY=<long-random-server-side-key>
```

`PORT` is supplied by the platform. `GITHUB_TOKEN` is optional. `OPENAI_API_KEY`
is not used by the current deterministic workflow; M4/LLM extraction is not
implemented. Apply `alembic upgrade head` before the API starts (the Compose
`migrate` service does this automatically).

Frontend build environment variable for split hosting:

```text
VITE_API_BASE_URL=https://<backend-host>
```

For the V9 same-origin topology, build with `VITE_API_BASE_URL=/` and keep the
backend unexposed behind the frontend Nginx proxy where private networking is
available. The value must be configured before the frontend image build because
Vite embeds it into the static assets.

The frontend also needs the runtime variable `BACKEND_UPSTREAM`, which the Nginx
entrypoint substitutes into `proxy_pass`:

```text
BACKEND_UPSTREAM=http://<backend-internal-host>:<port>
```

Use the backend service's **Connect > Internal** address from the Render
dashboard. Private networking requires the same region and workspace, and free
web services cannot receive private-network traffic. If private networking is
unavailable, use the backend's public HTTPS origin instead:

```text
BACKEND_UPSTREAM=https://<backend-host>
```

`BACKEND_UPSTREAM` must be an origin only: no path, query, fragment, or trailing
slash. Compose sets it to `http://backend:8000`. `VITE_API_BASE_URL` remains `/`
for this topology; changing it to the backend URL would bypass the Nginx proxy
and its server-side `X-API-Key` injection. The frontend entrypoint fails closed
if `BACKEND_UPSTREAM` is missing or malformed.

## Production smoke tests

Run these against your actual backend/frontend origins only after configuring
the deployment. Replace the placeholders; do not treat them as verified URLs.

```bash
curl -i https://<backend-host>/api/health
curl -i https://<backend-host>/api/github/repositories/microsoft/vscode
curl -i -H "X-API-Key: $API_KEY" \
  -X POST https://<backend-host>/api/github/repositories/microsoft/vscode/analysis
curl -i -H "X-API-Key: $API_KEY" https://<backend-host>/api/analyses
curl -i -H "X-API-Key: $API_KEY" https://<backend-host>/api/statistics
```

Expected results are `200` for health, GitHub reads, analysis creation, history,
and statistics when the database, API key, and upstream are healthy. Analysis
creation requires PostgreSQL and persists its result.

Document intake and extraction are also protected:

```bash
curl -i -H "X-API-Key: $API_KEY" \
  -F "file=@sample.txt;type=text/plain" \
  https://<backend-host>/api/documents
curl -i -H "X-API-Key: $API_KEY" \
  -X POST https://<backend-host>/api/documents/<document_id>/extractions
```

Expected results are `201` for a valid intake and a valid extraction attempt.
`404 document_not_found`, `409 document_not_extractable`, `413
document_too_large`, and `422` for invalid/unsupported uploads are the expected
error cases.

For split hosting, configure `CORS_ALLOWED_ORIGINS` to the exact frontend origin.
Protected endpoints require a server-side proxy so `API_KEY` never reaches the
browser; do not add `X-API-Key` to browser code or a `VITE_*` variable.
