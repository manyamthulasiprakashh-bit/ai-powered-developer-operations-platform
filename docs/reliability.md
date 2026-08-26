# V5 Robustness & Reliability

This document describes the implemented reliability controls. It is not a production availability claim, load-test report, chaos-test report, or deployment certification.

## Implemented now

### Failure model

GitHub failures are classified as timeout, connection/network failure, rate limit, upstream 5xx, upstream 4xx, malformed response, or internal error. Public responses retain the existing `detail` field and add `error`, `message`, and `retryable` metadata. Stack traces, paths, configuration, and secrets are not returned.

### Retry policy

Only read-only GitHub operations are retried. Timeouts, connection failures, HTTP 429, and HTTP 5xx responses are eligible. 400, 401, 403 without a rate-limit signal, 404, malformed data, and internal errors are not retried. `GITHUB_MAX_RETRIES`, `GITHUB_RETRY_BASE_DELAY_SECONDS`, and `GITHUB_RETRY_MAX_DELAY_SECONDS` bound the attempts and jittered delay. There are no mutating GitHub operations to retry.

### Circuit breaker

The process-local breaker starts `CLOSED`, counts retryable upstream failures, changes to `OPEN` at the configured threshold, and fails fast during its reset window. After cooldown it permits the configured half-open probe count. A successful probe closes the circuit; a failed probe reopens it. It stores no credentials or response data.

### Graceful degradation and health

The backend reports GitHub unavailability, rate limiting, timeouts, not-found results, and invalid requests distinctly. `/api/health` remains a lightweight liveness endpoint. `/api/ready` reports application configuration readiness and does not create GitHub traffic or claim GitHub availability.

### Correlation and logging

`X-Request-ID` is generated when absent, preserves a bounded valid incoming value, and is returned in the response. Request logs include the ID, method, path, status, and duration. Retry and cache events log operation/type information without tokens, headers, payloads, or repository keys.

### Cache and single-flight failure behavior

Cache read/write exceptions fall back to the upstream request or return the already fetched response. Cache failures are not exposed as API failures. Single-flight locks are released by normal async context management; loader exceptions are not cached, so a later request can retry. Coordination remains process-local.

## Limitations

The circuit breaker, cache, single-flight locks, and rate limiter are process-local. There is no distributed coordination, external metrics or tracing backend, production load testing, chaos testing, background job system, or multi-instance reliability validation. Retry duration is bounded by configured per-attempt timeouts, maximum attempts, and capped delays, but no global production SLO is claimed.

## Future V6 work

Add distributed breaker/cache/rate-limit state, centralized metrics, distributed tracing, background processing for repository synchronization and indexing, load and chaos testing, dependency fault-injection tests, and multi-instance validation. Authentication and authorization remain separate future concerns.