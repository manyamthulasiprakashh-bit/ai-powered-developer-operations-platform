export interface Repository {
  name: string;
  full_name: string;
  owner: string;
  description: string | null;
  private: boolean;
  default_branch: string;
  language: string | null;
  stars: number;
  forks: number;
  open_issues: number;
  html_url: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface Commit {
  sha: string;
  short_sha: string;
  message: string;
  author: string | null;
  author_email: string | null;
  committed_at: string | null;
  url: string | null;
}

export interface PullRequest {
  number: number;
  title: string;
  state: string;
  author: string | null;
  created_at: string | null;
  updated_at: string | null;
  merged_at: string | null;
  url: string | null;
}

export interface Issue {
  number: number;
  title: string;
  state: string;
  author: string | null;
  labels: string[];
  created_at: string | null;
  updated_at: string | null;
  url: string | null;
}

export interface RepositoryContent {
  name: string;
  path: string;
  type: 'file' | 'dir' | string;
  size: number | null;
  url: string | null;
}
