export async function fetchJson<T>(url: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set('Content-Type', 'application/json');

  const response = await fetch(url, {
    ...init,
    headers,
  });

  if (!response.ok) {
    let message = 'Unable to connect to the backend.';
    try {
      const payload = await response.json();
      if (payload && typeof payload.detail === 'string') {
        message = payload.detail;
      }
    } catch {
      // Ignore JSON parsing errors and fall back to the generic message.
    }
    throw new Error(message);
  }

  return (await response.json()) as T;
}
