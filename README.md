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
- `CORS_ALLOWED_ORIGINS`: comma-separated allowed frontend origins for browser access
- `GITHUB_API_URL`: optional override for the GitHub API endpoint; defaults to `https://api.github.com`
- `GITHUB_TOKEN`: optional GitHub token for higher rate limits; keep it out of source control
- `DATABASE_URL`: required when the app is connected to Postgres
- `VITE_API_BASE_URL`: frontend API base URL used for deployed backend requests

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
