#!/bin/sh
# Fail-fast guard for the same-origin demo frontend.
#
# Runs before the stock nginx entrypoint (which renders
# /etc/nginx/templates/*.template into /etc/nginx/conf.d). Refuses to start
# when the required server-side secrets are missing or malformed so the
# deployment never comes up in a half-configured state.
#
# The htpasswd paths and the wrapped entrypoint can be overridden for tests:
#   HTPASSWD_FILE         default /etc/nginx/auth/htpasswd
#   RENDER_HTPASSWD_FILE  default /etc/secrets/htpasswd
#   DOCKER_ENTRYPOINT     default /docker-entrypoint.sh
set -eu

HTPASSWD_FILE="${HTPASSWD_FILE:-/etc/nginx/auth/htpasswd}"
RENDER_HTPASSWD_FILE="${RENDER_HTPASSWD_FILE:-/etc/secrets/htpasswd}"
DOCKER_ENTRYPOINT="${DOCKER_ENTRYPOINT:-/docker-entrypoint.sh}"

# BACKEND_UPSTREAM is interpolated unescaped into an nginx `proxy_pass`
# directive. Require an origin only: no path, query, fragment, trailing slash,
# credentials, whitespace, or directive-breaking characters. Compose supplies
# the backend service address; Render supplies the backend's private or public
# origin.
upstream="${BACKEND_UPSTREAM:-}"
case "$upstream" in
    '')
        echo "[entrypoint] FATAL: BACKEND_UPSTREAM is not set; refusing to start the proxy." >&2
        exit 1
        ;;
    http://*|https://*) ;;
    *)
        echo "[entrypoint] FATAL: BACKEND_UPSTREAM must use http:// or https://." >&2
        exit 1
        ;;
esac

authority="${upstream#*://}"
case "$authority" in
    ''|*/*|*\?*|*\#*|*[!A-Za-z0-9.:-]*)
        echo "[entrypoint] FATAL: BACKEND_UPSTREAM must be an HTTP(S) origin with a hostname and optional port, no path, query, fragment, or trailing slash." >&2
        exit 1
        ;;
    *:*:*|*:)
        echo "[entrypoint] FATAL: BACKEND_UPSTREAM has an invalid host or port." >&2
        exit 1
        ;;
    *:*)
        host="${authority%:*}"
        port="${authority##*:}"
        ;;
    *)
        host="$authority"
        port=""
        ;;
esac
case "$host" in
    ''|.*|*.|*..*|-*|*-|*.-*|*-.*|*[!A-Za-z0-9.-]*)
        echo "[entrypoint] FATAL: BACKEND_UPSTREAM has an invalid hostname." >&2
        exit 1
        ;;
esac
if [ -n "$port" ]; then
    case "$port" in
        0*|*[!0-9]*)
            echo "[entrypoint] FATAL: BACKEND_UPSTREAM has an invalid port." >&2
            exit 1
            ;;
    esac
    if [ "$port" -gt 65535 ]; then
        echo "[entrypoint] FATAL: BACKEND_UPSTREAM port must be between 1 and 65535." >&2
        exit 1
    fi
fi

# API_KEY is interpolated unescaped into an nginx `proxy_set_header` directive,
# so it must not contain characters that can terminate the directive (notably
# `;`, `{`, `}`, quotes, whitespace, `$`, or newlines). Intended value is
# `openssl rand -hex 32` (64 hex characters); `_` and `-` are also accepted for
# base64url-style keys. Length bounds keep the rendered config sane.
API_KEY_MIN_LENGTH=16
API_KEY_MAX_LENGTH=128

key="${API_KEY:-}"
case "$key" in
    '')
        echo "[entrypoint] FATAL: API_KEY is not set; refusing to start the proxy." >&2
        exit 1
        ;;
    *[!A-Za-z0-9_-]*)
        echo "[entrypoint] FATAL: API_KEY contains unsupported characters; use [A-Za-z0-9_-] only." >&2
        exit 1
        ;;
esac

if [ "${#key}" -lt "$API_KEY_MIN_LENGTH" ] || [ "${#key}" -gt "$API_KEY_MAX_LENGTH" ]; then
    echo "[entrypoint] FATAL: API_KEY must be ${API_KEY_MIN_LENGTH}-${API_KEY_MAX_LENGTH} characters." >&2
    exit 1
fi

# Render mounts Secret Files at /etc/secrets/<filename> rather than at the
# Nginx auth path used by Compose. Bridge the fixed Render path only when the
# expected path is absent, so an explicit bind mount always wins. The symlink
# keeps the file read-only at its mounted location and leaves auth_basic intact.
if [ ! -e "$HTPASSWD_FILE" ] && [ -f "$RENDER_HTPASSWD_FILE" ]; then
    if ! ln -s "$RENDER_HTPASSWD_FILE" "$HTPASSWD_FILE"; then
        echo "[entrypoint] FATAL: could not link ${RENDER_HTPASSWD_FILE} to ${HTPASSWD_FILE}." >&2
        exit 1
    fi
fi

# A missing host bind mount can become a directory in the container, and `-s`
# alone would pass for a non-empty directory. Require a readable regular file
# with at least one `user:hash` entry. The file must also be readable by the
# container's nginx user (uid 101); that ownership cannot be checked from here
# without the actual host mount.
if [ ! -e "$HTPASSWD_FILE" ]; then
    echo "[entrypoint] FATAL: ${HTPASSWD_FILE} is missing; mount the owner htpasswd file or add a Render Secret File named htpasswd." >&2
    exit 1
fi
if [ -d "$HTPASSWD_FILE" ]; then
    echo "[entrypoint] FATAL: ${HTPASSWD_FILE} is a directory; mount the htpasswd file itself." >&2
    exit 1
fi
if [ ! -f "$HTPASSWD_FILE" ]; then
    echo "[entrypoint] FATAL: ${HTPASSWD_FILE} is not a regular file." >&2
    exit 1
fi
if [ ! -r "$HTPASSWD_FILE" ]; then
    echo "[entrypoint] FATAL: ${HTPASSWD_FILE} is not readable by the nginx user." >&2
    exit 1
fi
if [ ! -s "$HTPASSWD_FILE" ]; then
    echo "[entrypoint] FATAL: ${HTPASSWD_FILE} is empty." >&2
    exit 1
fi
if ! grep -q ':' "$HTPASSWD_FILE" 2>/dev/null; then
    echo "[entrypoint] FATAL: ${HTPASSWD_FILE} does not contain a user:hash entry." >&2
    exit 1
fi

exec "$DOCKER_ENTRYPOINT" "$@"
