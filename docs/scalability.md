# V4 Scalability

## Implemented now

GitHub I/O is available through an async `httpx.AsyncClient` with connection reuse, bounded maximum connections, and separate connect/read timeout settings. The API routes use async service methods while preserving existing response schemas and compatibility with synchronous test clients.

Read-heavy GitHub responses are stored in a bounded in-process TTL cache. Cache keys include the operation and all request parameters. Cache errors are not stored. A per-key single-flight lock prevents identical concurrent misses from issuing duplicate upstream requests in one process. Cache hit/miss logs contain only the operation name.

Pagination is bounded by `GITHUB_MAX_PER_PAGE` for list endpoints, and existing contents limits remain bounded. The shared GitHub client is closed during FastAPI lifespan shutdown. Health answers whether the process responds; readiness reports configuration readiness and does not falsely depend on GitHub or unused database functionality.

## Configuration

Use `GITHUB_CONNECT_TIMEOUT`, `GITHUB_READ_TIMEOUT`, `GITHUB_MAX_CONNECTIONS`, `GITHUB_MAX_KEEPALIVE_CONNECTIONS`, `GITHUB_MAX_PER_PAGE`, `CACHE_ENABLED`, `CACHE_TTL_SECONDS`, and `CACHE_MAX_ENTRIES`. Safe defaults are documented in `.env.example`.

## Process-local limitations

The cache, single-flight locks, and existing V3 rate limiter live in one process. They do not coordinate across workers or instances. Horizontal deployment would require a shared cache/lock and rate-limit store, plus externalized job state. No distributed cache, background worker, or production scale test is claimed by V4.

## Future candidates

Repository synchronization, periodic refresh, large content indexing, and analytics aggregation are candidates for a future background-job boundary. They remain synchronous or unimplemented today; Celery, Kafka, Redis, and other distributed systems are intentionally not introduced in V4.