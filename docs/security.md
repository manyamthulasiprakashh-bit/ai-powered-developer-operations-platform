# V3 Security & Compliance Hardening

This document describes implemented security controls and current limitations. It is not a compliance certification, penetration-test report, or production security audit.

## Threat model

The API accepts repository identifiers and bounded query parameters for public GitHub reads, plus protected document uploads and extraction requests. Protected routes require `X-API-Key`; public GitHub reads call the GitHub REST API. Relevant threats include abusive request volume, malformed or oversized input (including document uploads), accidental secret disclosure, hostile browser origins, and upstream failures that reveal internal details.

## Secrets management

Secrets remain server-side. `API_KEY`, `GITHUB_TOKEN`, `OPENAI_API_KEY`, and database credentials are environment variables; the owner Basic Auth credential is a secret file supplied by a Compose bind mount or, on Render, a Secret File. They are absent from frontend source and API responses. `.env.example` contains placeholders/local development values only; deployment secrets must come from the platform secret store. `OPENAI_API_KEY` is reserved for future LLM extraction and is not used by the current deterministic workflow (M4 is not implemented).

## CORS policy

CORS is environment-driven. Development permits local origins and the existing local tunnel pattern. Production requires explicitly configured absolute HTTPS origins. Wildcard origins are rejected and credentials are never combined with `allow_origins=["*"]`.

## Security headers

Responses include `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and a restrictive baseline Content Security Policy. Production responses also include HSTS. The CSP is intentionally conservative for this API and should be reviewed if API documentation assets or additional browser-hosted content change.

## Rate limiting

Non-health API requests use a configurable in-memory limiter (`RATE_LIMIT_REQUESTS` and `RATE_LIMIT_WINDOW_SECONDS`) keyed by client identity, HTTP method, and a stable route template rather than the raw URL, so repository owner/name cannot create a new bucket per path. Analysis creation uses a separate, stricter bucket (`RATE_LIMIT_ANALYSIS_REQUESTS`, default `10` per window) keyed by client identity only. Client identity is the direct peer address; `X-Forwarded-For` is honored only when the peer is listed in `TRUSTED_PROXY_IPS`, so untrusted clients cannot spoof that header. Exceeding a limit returns `429` with `Retry-After`. Health, readiness, and metrics endpoints are exempt. The limiter is process-local and is not a distributed control: limits reset on restart and are not shared across workers or replicas, and it has a replaceable interface for a later shared-store implementation.

## Input validation

Pagination values retain their existing positive and maximum bounds. Owner and repository path segments are restricted to safe GitHub identifier characters and length. Repository content paths have a maximum length and reject parent-directory traversal segments. Document intake validates the extension, media type, strict UTF-8 decoding, non-empty text, exact file size, text length, and the whole multipart request cap; the stored body is never returned in full.

## Error handling and logging

Known GitHub failures map to stable status codes. Public error responses do not contain stack traces, filesystem paths, configuration, or secret values. Request logs include method, path, status, and duration, while sensitive key/value patterns are redacted and request bodies, authorization headers, cookies, and tokens are not logged.

## Container security

The backend image runs as a non-root user and installs pinned Python requirements without bytecode compilation. The frontend uses a multi-stage build and the unprivileged Nginx image, so development tooling is not present in the runtime image. No secret files are copied into either image. Compose bind-mounts the owner Basic Auth file read-only at `/etc/nginx/auth/htpasswd`. On Render, a Secret File named `htpasswd` is mounted at `/etc/secrets/htpasswd`; the frontend entrypoint creates a symlink at `/etc/nginx/auth/htpasswd` only when the bind-mounted path is absent. Render exposes Secret Files through group GID 1000, and the image adds the nginx user (UID 101) to that group so the unprivileged process can read the file. `frontend/.dockerignore` excludes `htpasswd` from the Docker build context. The backend `API_KEY` is rendered into the frontend container's Nginx config at start from an environment variable (never baked into an image layer or the built assets).

## Dependency and CI scanning

CI runs backend tests, frontend validation/build, `pip-audit`, and `npm audit --audit-level=high`. These checks require network access in GitHub Actions and were not run locally during this review unless explicitly reported in the final validation notes.

## Authentication boundary

Analysis creation (`POST /api/github/repositories/{owner}/{repo}/analysis`), the stored-analysis endpoints (`GET /api/analyses`, `GET /api/analyses/{analysis_id}`, `GET /api/statistics`), document intake (`POST /api/documents`), and deterministic extraction (`POST /api/documents/{document_id}/extractions`) require a server-side API key supplied in the `X-API-Key` header (`API_KEY`). The comparison is constant-time and the supplied value is never logged or returned. Missing or invalid credentials return a consistent `401` (`{"error": "unauthorized"}`). If authentication is required but `API_KEY` is not configured, the protected endpoints **fail closed** with `503` rather than disabling protection. The GitHub read endpoints (repository metadata, commits, pull requests, issues, contents), `/api/health`, `/api/ready`, `/health`, `/ready`, `/metrics`, `/docs`, `/redoc`, and the root response remain public.

This is a single shared key, not a user system. There is **no data isolation between authorized callers**: anyone holding the key can read all persisted analyses and statistics and can submit or extract documents, and there is no per-user or per-repository ownership model. The key is a shared deployment secret and must be rotated if disclosed. It cannot be safely embedded in the browser frontend, so browser clients of the protected endpoints require a server-side proxy.

### Browser access: owner Basic Auth + same-origin proxy

For the single-owner public demo, the SPA and the API are served from one origin by the frontend Nginx container:

- The whole server (SPA and `/api/`) is gated by Nginx `auth_basic` with a single owner credential (`/etc/nginx/auth/htpasswd`). Compose bind-mounts that file read-only; on Render, the entrypoint symlinks it from the gitignored Secret File at `/etc/secrets/htpasswd`. Owner access is authenticated by that Basic Auth credential over HTTPS; the proxy is not an open relay.
- `/api/` is reverse-proxied to the backend with `X-API-Key` injected server-side from the `API_KEY` environment variable at container start. The key is rendered into the in-container Nginx config and never appears in frontend source, `VITE_*` values, built assets, browser storage, or responses.
- The SPA is built with `VITE_API_BASE_URL=/` and issues relative `/api/...` requests, so no CORS or cross-origin cookie handling is involved.
- The proxy overwrites `X-Forwarded-For`/`X-Real-IP` with the connecting client address rather than appending client-supplied values, and the backend honors those headers only from the proxy address listed in `TRUSTED_PROXY_IPS` (matching the frontend container's static address on the `edge` network).
- The backend and database publish no host ports; the backend is reachable only from the frontend proxy.

Limitations of this edge: Basic Auth is a single shared credential with no per-user identity, MFA, or per-session revocation, and it is not rate-limited at the edge; it must be served over HTTPS because the credential is sent on every request. It authenticates "the owner" only and is appropriate for a single-owner demo, not multi-user access.


## Known limitations and future improvements

There is no user-management system, per-user data isolation, authorization model, distributed rate limiting, independent audit service, metrics/tracing backend, automated secret-scanning result, or penetration test evidence. The `audit_events` table is written internally for document lifecycle events and exposed read-only through the document detail and audit endpoints. The API key is a single shared secret and the rate limiter is process-local. Future work should add identity and least-privilege access, shared rate-limit state, secret scanning, retention/access policies, and an independently reviewed production security posture. This project does not claim SOC 2, ISO 27001, GDPR, or other certification.
