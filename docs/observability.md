# V6 Observability

V6 provides local, dependency-free observability foundations for diagnosing requests and GitHub failures. It does not add or claim a hosted monitoring platform, production dashboards, SLOs, or external alerting.

## Architecture

The FastAPI middleware owns request correlation, HTTP counters, duration observation, security headers, and request completion logs. The existing GitHub client records upstream attempts, failures, durations, retry attempts, and circuit openings. The existing V4 cache records bounded hit/miss counters. All metrics are process-local and exposed as JSON from `/metrics`.

## Logging format

Backend logs are JSON records containing a UTC timestamp, level, logger, message, and bounded event fields. HTTP events include request ID, method, path, status, and duration. GitHub events include operation/error type and retry count where relevant. Exception output contains only the exception class, not traceback text, in the JSON formatter.

Sensitive values are not logged: tokens, authorization headers, cookies, API keys, database credentials, request bodies, and full upstream payloads are excluded or redacted. Request IDs accept only bounded safe characters and are never authentication credentials.

## Request IDs

`X-Request-ID` is reused when it matches the safe bounded format; otherwise a UUID is generated. The ID is placed in request state, included in request logs, and returned in the response header. It is correlation metadata only.

## Metrics

The `/metrics` endpoint reports stable aggregate names such as `http_requests_total`, `http_errors_total`, `http_request_duration_seconds`, `github_requests_total`, `github_failures_total`, `github_request_duration_seconds`, `github_retry_attempts_total`, `github_circuit_openings_total`, `cache_hits_total`, and `cache_misses_total`. There are no arbitrary URL, repository, query-string, or request-ID labels. Metrics contain no credentials or payloads.

## Health and readiness

`/health` and `/api/health` are lightweight process-liveness checks. `/ready` and `/api/ready` report configuration readiness based on the current architecture and do not call GitHub or falsely claim unused PostgreSQL request readiness.

## Failure diagnosis

Use the response `X-Request-ID` to correlate a client failure with `request_started`, `request_completed`, `request_failed`, retry, circuit, GitHub, and cache events. Stable API error metadata identifies invalid requests, upstream unavailability, timeouts, rate limits, and circuit-open responses while retaining the V5 `detail` field.

## Local usage and limitations

Run the existing backend locally, call `/health`, `/ready`, and `/metrics`, and inspect JSON logs from the process. CI validates tests, lint/build, and dependency checks, but no external monitoring is configured. Metrics and logs are process-local, there is no metrics retention or alerting, and Docker/deployed observability has not been independently verified in this environment.