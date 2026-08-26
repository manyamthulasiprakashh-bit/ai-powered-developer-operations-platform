# API Design

## Health

- GET /api/health

Returns a lightweight status payload used for monitoring and Docker health checks.

- GET /api/ready

Returns deterministic configuration readiness. It does not make a GitHub request or claim PostgreSQL availability because the current API does not use the database at request time.

## Future endpoints

The project is structured for the following API surface in later phases:

- GET /api/repositories
- POST /api/repositories/connect
- GET /api/repositories/{id}
- GET /api/repositories/{id}/commits
- GET /api/repositories/{id}/pull-requests
- POST /api/repositories/{id}/analyze
- POST /api/incidents/analyze
- POST /api/ai/chat
- GET /api/analyses
- GET /api/analyses/{id}
- GET /api/statistics

These endpoints will be backed by dedicated service modules and validation schemas once the integration phase begins.
