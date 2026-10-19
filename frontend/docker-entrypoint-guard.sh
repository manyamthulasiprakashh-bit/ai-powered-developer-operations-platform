#!/bin/sh
# Fail-fast guard for the same-origin demo frontend.
#
# Runs before the stock nginx entrypoint (which renders
# /etc/nginx/templates/*.template into /etc/nginx/conf.d). Refuses to start
# when the required server-side secrets are missing or malformed so the
# deployment never comes up in a half-configured state.
#
# The htpasswd path and the wrapped entrypoint can be overridden for tests:
#   HTPASSWD_FILE      default /etc/nginx/auth/htpasswd
#   DOCKER_ENTRYPOINT  default /docker-entrypoint.sh
set -eu

HTPASSWD_FILE="${HTPASSWD_FILE:-/etc/nginx/auth/htpasswd}"
DOCKER_ENTRYPOINT="${DOCKER_ENTRYPOINT:-/docker-entrypoint.sh}"

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

# A missing host bind mount can become a directory in the container, and `-s`
# alone would pass for a non-empty directory. Require a readable regular file
# with at least one `user:hash` entry. The file must also be readable by the
# container's nginx user (uid 101); that ownership cannot be checked from here
# without the actual host mount.
if [ ! -e "$HTPASSWD_FILE" ]; then
    echo "[entrypoint] FATAL: ${HTPASSWD_FILE} is missing; mount the owner htpasswd file." >&2
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
