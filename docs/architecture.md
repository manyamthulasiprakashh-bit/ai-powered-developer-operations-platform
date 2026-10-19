# Architecture

This project follows a layered monolith-friendly architecture intended to scale into a more modular service later without introducing unnecessary complexity.

## Layers

- Presentation layer: React + TypeScript dashboard and views
- API layer: FastAPI application with route modules and validation schemas
- Service layer: GitHub, deterministic repository analysis, document intake, and deterministic extraction
- Data layer: SQLAlchemy models and PostgreSQL persistence
- Integration layer: GitHub REST adapter; LLM extraction is planned but not implemented (M4)

## Design Principles

- clear separation of concerns
- environment-based configuration
- minimal external coupling
- structured outputs over ad hoc prompts
- no automatic execution of AI-generated commands
- no secrets in source control

## Phase 1 Decisions

The initial foundation keeps the app runnable with a minimal API and frontend shell. The backend is bootstrapped with health checking and environment settings, and the frontend renders a basic dashboard shell. This allows the project to be run quickly, tested, and extended through the remaining phases without overbuilding the architecture too early.

## Document extraction concurrency

A document is claimed with a single conditional `UPDATE` that moves it to
`extracting` and writes the `extraction_started` audit event in the same
transaction. Under PostgreSQL's default isolation level, the row lock makes the
claim single-winner; a rejected claim writes no start event, and a failed claim
rolls back the status change and event together.

Current limitations:

- The lease is fixed at 300 seconds and is based on the claim/finalization
  timestamp. There is no heartbeat or renewal.
- Finalization is not yet fenced by an attempt token. If extraction work exceeds
  the lease, another worker can reclaim the document, and a later-completing
  stale worker can overwrite the newer result (the write is last-writer-wins).
- The deterministic extractor is local and expected to finish well within the
  lease, but PostgreSQL concurrency behavior has not been tested locally. The
  automated suite runs sequential in-memory SQLite tests.
- M4 must add ownership-token fencing, a heartbeat or renewable lease, and
  PostgreSQL concurrency tests before variable-duration LLM extraction is
  enabled.

This is not a claim of production-grade concurrency safety.

## Audit retention

Audit history should be preserved when document deletion is introduced. The
current models and the applied `0002_create_documents` migration use
`ON DELETE CASCADE`, so a hard delete would remove audit events together with
extraction and decision history. The future deletion design should prefer soft
deletion (for example, a `deleted_at` column on `documents`) and a new migration
that changes the relevant foreign keys to `RESTRICT`, or an explicit, audited
erasure procedure. Do not edit `0002_create_documents.py` in place; add a new
revision when deletion behavior is implemented.
