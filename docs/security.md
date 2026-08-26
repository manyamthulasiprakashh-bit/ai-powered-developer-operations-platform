# V3 Security & Compliance Hardening

This document describes implemented security controls and current limitations. It is not a compliance certification, penetration-test report, or production security audit.

## Threat model

The public API accepts repository identifiers and read-only query parameters, then calls the GitHub REST API. Relevant threats include abusive request volume, malformed or oversized input, accidental secret disclosure, hostile browser origins, and upstream failures that reveal internal details.

## Secrets management

Secrets remain server-side environment variables, including `GITHUB_TOKEN`, `OPENAI_API_KEY`, and database credentials. They are absent from frontend source and API responses. `.env.example` contains placeholders/local development values only; deployment secrets must come from the platform secret store.

## CORS policy

CORS is environment-driven. Development permits local origins and the existing local tunnel pattern. Production requires explicitly configured absolute HTTPS origins. Wildcard origins are rejected and credentials are never combined with `allow_origins=["*"]`.

## Security headers

Responses include `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and a restrictive baseline Content Security Policy. Production responses also include HSTS. The CSP is intentionally conservative for this API and should be reviewed if API documentation assets or additional browser-hosted content change.

## Rate limiting

Non-health API requests use a configurable in-memory limiter (`RATE_LIMIT_REQUESTS` and `RATE_LIMIT_WINDOW_SECONDS`) keyed by client and endpoint. Exceeding the limit returns `429` with `Retry-After`. Health and readiness endpoints are exempt. The limiter is process-local and is not sufficient as a distributed production control; it has a replaceable interface for a later shared-store implementation.

## Input validation

Pagination values retain their existing positive and maximum bounds. Owner and repository path segments are restricted to safe GitHub identifier characters and length. Repository content paths have a maximum length and reject parent-directory traversal segments.

## Error handling and logging

Known GitHub failures map to stable status codes. Public error responses do not contain stack traces, filesystem paths, configuration, or secret values. Request logs include method, path, status, and duration, while sensitive key/value patterns are redacted and request bodies, authorization headers, cookies, and tokens are not logged.

## Container security

The backend image runs as a non-root user and installs pinned Python requirements without bytecode compilation. The frontend uses a multi-stage build and the unprivileged Nginx image, so development tooling is not present in the runtime image. No secret files are copied into either image.

## Dependency and CI scanning

CI runs backend tests, frontend validation/build, `pip-audit`, and `npm audit --audit-level=high`. These checks require network access in GitHub Actions and were not run locally during this review unless explicitly reported in the final validation notes.

## Authentication boundary

All current repository intelligence endpoints, health endpoints, and the root response are public read-only endpoints. No user-management system or credentials were added. Authentication can be introduced as a dependency at the API router boundary before write operations or private repository access are added.

## Known limitations and future improvements

There is no authentication, authorization, distributed rate limiting, audit event store, metrics/tracing backend, automated secret-scanning result, or penetration test evidence. Future work should add identity and least-privilege access, shared rate-limit state, secret scanning, retention/access policies, and an independently reviewed production security posture. This project does not claim SOC 2, ISO 27001, GDPR, or other certification.
