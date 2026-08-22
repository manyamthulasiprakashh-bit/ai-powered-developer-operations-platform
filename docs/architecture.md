# Architecture

This project follows a layered monolith-friendly architecture intended to scale into a more modular service later without introducing unnecessary complexity.

## Layers

- Presentation layer: React + TypeScript dashboard and views
- API layer: FastAPI application with route modules and validation schemas
- Service layer: GitHub, repository analysis, AI, and incident logic
- Data layer: SQLAlchemy models and PostgreSQL persistence
- Integration layer: GitHub and LLM adapters behind interfaces

## Design Principles

- clear separation of concerns
- environment-based configuration
- minimal external coupling
- structured outputs over ad hoc prompts
- no automatic execution of AI-generated commands
- no secrets in source control

## Phase 1 Decisions

The initial foundation keeps the app runnable with a minimal API and frontend shell. The backend is bootstrapped with health checking and environment settings, and the frontend renders a basic dashboard shell. This allows the project to be run quickly, tested, and extended through the remaining phases without overbuilding the architecture too early.
