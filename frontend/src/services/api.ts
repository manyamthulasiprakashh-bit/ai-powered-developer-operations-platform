export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly retryable: boolean;

  constructor(message: string, status: number, code?: string, retryable = false) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.retryable = retryable;
  }
}

function fallbackMessage(status: number): string {
  if (status === 401) return 'Unauthorized.';
  if (status === 413) return 'Uploaded document is too large.';
  if (status === 429) return 'Too many requests. Please wait and try again.';
  if (status >= 500) return 'The server could not complete the request.';
  return 'Unable to complete the request.';
}

async function toApiError(response: Response): Promise<ApiError> {
  let message = fallbackMessage(response.status);
  let code: string | undefined;
  let retryable = response.status >= 500 || response.status === 429;

  try {
    const payload = (await response.json()) as {
      detail?: unknown;
      message?: unknown;
      error?: unknown;
      retryable?: unknown;
    };
    if (typeof payload.detail === 'string' && payload.detail.trim()) {
      message = payload.detail;
    } else if (typeof payload.message === 'string' && payload.message.trim()) {
      message = payload.message;
    }
    if (typeof payload.error === 'string') code = payload.error;
    if (typeof payload.retryable === 'boolean') retryable = payload.retryable;
  } catch {
    // Non-JSON responses (for example an Nginx error page) use the safe fallback.
  }

  return new ApiError(message, response.status, code, retryable);
}

export async function fetchJson<T>(url: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const isFormData = typeof FormData !== 'undefined' && init.body instanceof FormData;
  if (!isFormData && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new Error('Unable to connect to the backend.');
  }

  if (!response.ok) {
    throw await toApiError(response);
  }

  const text = await response.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}
