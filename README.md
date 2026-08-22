# AI-Powered Developer Operations Platform

A production-style portfolio project for AI-assisted developer operations and debugging workflows.

## Overview

This platform helps engineering teams connect to a GitHub repository, inspect code and change history, analyze incidents, and get AI-powered explanations and remediation suggestions. The project intentionally follows a clean separation between frontend, backend, integrations, AI services, and data persistence.

## Phase 1 Foundation

This repository currently includes the initial foundation for the project:

- FastAPI backend skeleton
- environment-driven configuration
- request logging middleware
- health endpoint
- PostgreSQL-ready SQLAlchemy setup using a binary-compatible PostgreSQL driver
- Docker-ready project layout
- initial frontend scaffold
- project documentation skeleton

## Architecture

- Frontend: React + TypeScript + Vite + Tailwind
- Backend: Python + FastAPI + SQLAlchemy + Pydantic
- Data layer: PostgreSQL
- Infrastructure: Docker + Docker Compose
- AI: provider abstraction ready for LLM integration

## Features Included in Phase 1

- health endpoint at `/api/health`
- backend app bootstrap
- configuration management
- structured logging setup
- Docker-ready structure
- repository skeleton for later phases

## Setup

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

### Environment

Copy the sample environment file and adjust values if needed:

```bash
cp .env.example .env
```

## Running with Docker

```bash
docker compose up --build
```

## Testing

```bash
cd backend
pytest
```

## Documentation

- [docs/architecture.md](docs/architecture.md)
- [docs/api.md](docs/api.md)
- [docs/development.md](docs/development.md)

## Future Improvements

- GitHub repository integration
- repository analyzer
- AI-powered debugging workflows
- incident and log analysis
- dashboard UI and API endpoints
- robust database models and migrations
