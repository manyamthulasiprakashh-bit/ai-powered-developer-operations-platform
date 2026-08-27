# Development Guide

## Local Setup

1. Create a Python environment in the backend folder.
2. Install dependencies from `backend/requirements.txt`.
3. Copy `.env.example` to `.env` and adjust values.
4. Start the backend with Uvicorn.
5. Start the frontend with Vite.

## Running Tests

```bash
cd backend
pytest
```

## Docker

```bash
docker compose up --build
```

## Render deployment

This repository does not contain a Render manifest. Configure the two Render
services from the repository root using the existing Dockerfiles:

| Service | Root directory | Dockerfile | Runtime/build behavior |
| --- | --- | --- | --- |
| Backend | `backend` | `Dockerfile` | The image starts Uvicorn on Render's `PORT`. |
| Frontend | `frontend` | `Dockerfile` | The image runs `npm run build`, then serves `dist` with Nginx. |

Both services must build from the branch containing the V1 analysis changes.
The branch is a Render service setting and cannot be verified from this
repository. Do not set a root directory to the parent repository when using
these Dockerfiles.

Backend environment variables:

```text
APP_ENV=production
APP_DEBUG=false
CORS_ALLOWED_ORIGINS=https://ai-powered-developer-operations-platform.onrender.com
```

`PORT` is supplied by Render. `GITHUB_API_URL` defaults to GitHub's public API
and `GITHUB_TOKEN` is optional. OpenAI and PostgreSQL are not required by V1.

Frontend build environment variable:

```text
VITE_API_BASE_URL=https://ai-powered-developer-operations-backend.onrender.com
```

This value must be configured before the frontend image build because Vite
embeds it into the generated static assets. The frontend service does not need
a runtime environment variable for this setting.

## Production smoke test

After both services redeploy, run these checks against the public backend:

```bash
curl -i https://ai-powered-developer-operations-backend.onrender.com/api/health
curl -i https://ai-powered-developer-operations-backend.onrender.com/api/github/repositories/microsoft/vscode
curl -i -X POST https://ai-powered-developer-operations-backend.onrender.com/api/github/repositories/microsoft/vscode/analysis
curl -i -X OPTIONS \
	-H 'Origin: https://ai-powered-developer-operations-platform.onrender.com' \
	-H 'Access-Control-Request-Method: GET' \
	-H 'Access-Control-Request-Headers: content-type,bypass-tunnel-reminder' \
	https://ai-powered-developer-operations-backend.onrender.com/api/github/repositories/microsoft/vscode
```

Expected results are `200`, `200`, and `200` for the first three requests. The
preflight should return `200` and include
`Access-Control-Allow-Origin: https://ai-powered-developer-operations-platform.onrender.com`.

## Validation Focus for Phase 1

- backend health endpoint returns 200
- app boots without import errors
- frontend builds successfully
- environment variables are documented and sample values exist
