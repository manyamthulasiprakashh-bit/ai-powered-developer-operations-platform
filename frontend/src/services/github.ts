import { API_BASE_URL } from '../config';
import type { Commit, Issue, PullRequest, Repository, RepositoryContent } from '../types';

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { headers: { 'Content-Type': 'application/json' } });

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

export async function getRepository(owner: string, repo: string): Promise<Repository> {
  const url = `${API_BASE_URL}/api/github/repositories/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}`;
  return fetchJson<Repository>(url);
}

export async function getCommits(
  owner: string,
  repo: string,
  page = 1,
  perPage = 10,
): Promise<Commit[]> {
  const url = `${API_BASE_URL}/api/github/repositories/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/commits?page=${page}&per_page=${perPage}`;
  return fetchJson<Commit[]>(url);
}

export async function getPullRequests(
  owner: string,
  repo: string,
  state: 'open' | 'closed' | 'all' = 'open',
  page = 1,
  perPage = 10,
): Promise<PullRequest[]> {
  const url = `${API_BASE_URL}/api/github/repositories/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/pull-requests?state=${state}&page=${page}&per_page=${perPage}`;
  return fetchJson<PullRequest[]>(url);
}

export async function getIssues(
  owner: string,
  repo: string,
  state: 'open' | 'closed' | 'all' = 'open',
  page = 1,
  perPage = 10,
): Promise<Issue[]> {
  const url = `${API_BASE_URL}/api/github/repositories/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/issues?state=${state}&page=${page}&per_page=${perPage}`;
  return fetchJson<Issue[]>(url);
}

export async function getContents(
  owner: string,
  repo: string,
  page = 1,
  perPage = 30,
): Promise<RepositoryContent[]> {
  const url = `${API_BASE_URL}/api/github/repositories/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/contents?page=${page}&per_page=${perPage}`;
  return fetchJson<RepositoryContent[]>(url);
}
