const rawApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();

// Same-origin sentinels: when the SPA is served by the same origin that proxies
// /api (the public-demo Nginx deployment), VITE_API_BASE_URL is set to one of
// these and requests use relative /api/... URLs.
const SAME_ORIGIN_VALUES = new Set(['/', '.', 'relative']);
const isSameOrigin = rawApiBaseUrl !== undefined && SAME_ORIGIN_VALUES.has(rawApiBaseUrl);

if (import.meta.env.PROD && !isSameOrigin && !rawApiBaseUrl) {
  throw new Error('VITE_API_BASE_URL must be configured for production builds.');
}

export const API_BASE_URL = isSameOrigin
  ? ''
  : (rawApiBaseUrl || 'http://localhost:8000').replace(/\/+$/, '');
