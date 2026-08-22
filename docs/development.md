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

## Validation Focus for Phase 1

- backend health endpoint returns 200
- app boots without import errors
- frontend builds successfully
- environment variables are documented and sample values exist
