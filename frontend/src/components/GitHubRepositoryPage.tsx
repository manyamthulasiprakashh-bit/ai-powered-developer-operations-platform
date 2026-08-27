import React, { useEffect, useMemo, useRef, useState } from 'react';
import { analyzeRepository, getCommits, getContents, getIssues, getPullRequests, getRepository } from '../services/github';
import type { AnalysisSeverity, Commit, Issue, PullRequest, Repository, RepositoryAnalysis, RepositoryContent } from '../types';

interface GitHubRepositoryPageProps {
  owner?: string;
  repo?: string;
  onNavigate: (path: string) => void;
}

const defaultIssueState = 'open';
const defaultPullRequestState = 'open';

function formatDate(value: string | null): string {
  if (!value) return 'N/A';
  return new Date(value).toLocaleString();
}

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 p-5 shadow-lg shadow-slate-950/30">
      <h3 className="mb-4 text-lg font-semibold text-slate-100">{title}</h3>
      {children}
    </section>
  );
}

function RepositoryHeader({ repository }: { repository: Repository | null }) {
  if (!repository) return null;

  return (
    <div className="mb-6 rounded-xl border border-slate-800 bg-slate-900 p-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-sm uppercase tracking-[0.2em] text-cyan-400">Repository</p>
          <h2 className="mt-2 text-3xl font-bold text-white">{repository.name}</h2>
          <p className="mt-2 text-sm text-slate-400">{repository.full_name}</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="rounded-full border border-slate-700 bg-slate-950 px-3 py-1 text-sm text-slate-300">
            {repository.private ? 'Private' : 'Public'}
          </span>
          <a
            href={repository.html_url}
            target="_blank"
            rel="noreferrer"
            className="rounded-lg bg-cyan-500 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-cyan-400"
          >
            View on GitHub
          </a>
        </div>
      </div>
    </div>
  );
}

function RepositoryStats({ repository }: { repository: Repository | null }) {
  if (!repository) return null;

  const stats = [
    ['Stars', repository.stars.toLocaleString()],
    ['Forks', repository.forks.toLocaleString()],
    ['Open issues', repository.open_issues.toLocaleString()],
    ['Default branch', repository.default_branch],
  ];

  return (
    <div className="mb-6 grid gap-4 md:grid-cols-4">
      {stats.map(([label, value]) => (
        <div key={label} className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          <p className="text-sm text-slate-400">{label}</p>
          <p className="mt-2 text-2xl font-semibold text-white">{value}</p>
        </div>
      ))}
    </div>
  );
}

function RepositoryMetadata({ repository }: { repository: Repository | null }) {
  if (!repository) return null;

  return (
    <SectionCard title="Repository metadata">
      <div className="grid gap-4 md:grid-cols-2">
        <dl className="space-y-3 text-sm">
          <div className="flex justify-between gap-4 border-b border-slate-800 pb-2">
            <dt className="text-slate-400">Description</dt>
            <dd className="text-right text-slate-100">{repository.description || 'No description provided'}</dd>
          </div>
          <div className="flex justify-between gap-4 border-b border-slate-800 pb-2">
            <dt className="text-slate-400">Language</dt>
            <dd className="text-slate-100">{repository.language || 'Unknown'}</dd>
          </div>
          <div className="flex justify-between gap-4 border-b border-slate-800 pb-2">
            <dt className="text-slate-400">Created</dt>
            <dd className="text-slate-100">{formatDate(repository.created_at)}</dd>
          </div>
        </dl>
        <dl className="space-y-3 text-sm">
          <div className="flex justify-between gap-4 border-b border-slate-800 pb-2">
            <dt className="text-slate-400">Default branch</dt>
            <dd className="text-slate-100">{repository.default_branch}</dd>
          </div>
          <div className="flex justify-between gap-4 border-b border-slate-800 pb-2">
            <dt className="text-slate-400">GitHub URL</dt>
            <dd className="truncate text-slate-100">
              <a href={repository.html_url} target="_blank" rel="noreferrer" className="text-cyan-400 hover:underline">
                {repository.html_url}
              </a>
            </dd>
          </div>
          <div className="flex justify-between gap-4 border-b border-slate-800 pb-2">
            <dt className="text-slate-400">Last updated</dt>
            <dd className="text-slate-100">{formatDate(repository.updated_at)}</dd>
          </div>
        </dl>
      </div>
    </SectionCard>
  );
}

function CommitList({ commits }: { commits: Commit[] }) {
  if (!commits.length) {
    return <p className="text-sm text-slate-400">No commits found for this repository.</p>;
  }

  return (
    <div className="space-y-3">
      {commits.map((commit) => (
        <div key={commit.sha} className="rounded-lg border border-slate-800 bg-slate-950 p-3">
          <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="font-medium text-slate-100">{commit.message.split('\n')[0]}</p>
              <p className="mt-1 text-xs text-slate-400">{commit.author || 'Unknown author'} • {commit.short_sha}</p>
            </div>
            <div className="text-xs text-slate-400">{formatDate(commit.committed_at)}</div>
          </div>
          {commit.url ? (
            <a href={commit.url} target="_blank" rel="noreferrer" className="mt-3 inline-block text-xs text-cyan-400 hover:underline">
              Open commit
            </a>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function PullRequestList({ pullRequests, state, onStateChange }: { pullRequests: PullRequest[]; state: 'open' | 'closed' | 'all'; onStateChange: (value: 'open' | 'closed' | 'all') => void }) {
  return (
    <SectionCard title="Pull requests">
      <div className="mb-4 flex flex-wrap gap-2">
        {(['open', 'closed', 'all'] as const).map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => onStateChange(option)}
            className={`rounded-full border px-3 py-1.5 text-sm transition ${
              state === option
                ? 'border-cyan-500 bg-cyan-500/10 text-cyan-300'
                : 'border-slate-700 bg-slate-950 text-slate-300 hover:border-slate-600'
            }`}
          >
            {option.charAt(0).toUpperCase() + option.slice(1)}
          </button>
        ))}
      </div>
      {!pullRequests.length ? (
        <p className="text-sm text-slate-400">No pull requests match the selected state.</p>
      ) : (
        <div className="space-y-3">
          {pullRequests.map((pr) => (
            <div key={pr.number} className="rounded-lg border border-slate-800 bg-slate-950 p-3">
              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="font-medium text-slate-100">#{pr.number} • {pr.title}</p>
                  <p className="mt-1 text-xs text-slate-400">{pr.author || 'Unknown author'} • {pr.state}</p>
                </div>
                <div className="text-xs text-slate-400">{formatDate(pr.updated_at)}</div>
              </div>
              {pr.url ? (
                <a href={pr.url} target="_blank" rel="noreferrer" className="mt-3 inline-block text-xs text-cyan-400 hover:underline">
                  Open pull request
                </a>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  );
}

function IssueList({ issues, state, onStateChange }: { issues: Issue[]; state: 'open' | 'closed' | 'all'; onStateChange: (value: 'open' | 'closed' | 'all') => void }) {
  return (
    <SectionCard title="Issues">
      <div className="mb-4 flex flex-wrap gap-2">
        {(['open', 'closed', 'all'] as const).map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => onStateChange(option)}
            className={`rounded-full border px-3 py-1.5 text-sm transition ${
              state === option
                ? 'border-cyan-500 bg-cyan-500/10 text-cyan-300'
                : 'border-slate-700 bg-slate-950 text-slate-300 hover:border-slate-600'
            }`}
          >
            {option.charAt(0).toUpperCase() + option.slice(1)}
          </button>
        ))}
      </div>
      {!issues.length ? (
        <p className="text-sm text-slate-400">No issues match the selected state.</p>
      ) : (
        <div className="space-y-3">
          {issues.map((issue) => (
            <div key={issue.number} className="rounded-lg border border-slate-800 bg-slate-950 p-3">
              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="font-medium text-slate-100">#{issue.number} • {issue.title}</p>
                  <p className="mt-1 text-xs text-slate-400">{issue.author || 'Unknown author'} • {issue.state}</p>
                  {issue.labels.length ? (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {issue.labels.map((label) => (
                        <span key={label} className="rounded-full border border-slate-700 bg-slate-900 px-2 py-1 text-[10px] uppercase tracking-wide text-slate-300">
                          {label}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
                <div className="text-xs text-slate-400">{formatDate(issue.updated_at)}</div>
              </div>
              {issue.url ? (
                <a href={issue.url} target="_blank" rel="noreferrer" className="mt-3 inline-block text-xs text-cyan-400 hover:underline">
                  Open issue
                </a>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  );
}

function ContentList({ contents }: { contents: RepositoryContent[] }) {
  if (!contents.length) {
    return <p className="text-sm text-slate-400">No repository contents found.</p>;
  }

  return (
    <div className="space-y-2">
      {contents.map((item) => (
        <div key={`${item.path}-${item.name}`} className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-950 p-3 text-sm">
          <div>
            <p className="font-medium text-slate-100">{item.name}</p>
            <p className="text-xs text-slate-400">{item.path}</p>
          </div>
          <div className="flex items-center gap-3 text-xs text-slate-400">
            <span className="rounded-full border border-slate-700 px-2 py-1 uppercase tracking-wide text-slate-300">
              {item.type}
            </span>
            <span>{item.size != null ? `${item.size} B` : '—'}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

const severityStyles: Record<AnalysisSeverity, string> = {
  CRITICAL: 'border-rose-500/50 bg-rose-500/10 text-rose-300',
  HIGH: 'border-orange-500/50 bg-orange-500/10 text-orange-300',
  MEDIUM: 'border-yellow-500/50 bg-yellow-500/10 text-yellow-300',
  LOW: 'border-cyan-500/50 bg-cyan-500/10 text-cyan-300',
  INFO: 'border-slate-700 bg-slate-900 text-slate-300',
};

function AnalysisResults({ analysis }: { analysis: RepositoryAnalysis }) {
  const metrics = [
    ['Commits', analysis.metrics.commit_count],
    ['Open issues', analysis.metrics.open_issue_count],
    ['Open pull requests', analysis.metrics.open_pull_request_count],
    ['Root items', analysis.metrics.root_content_count],
  ];

  return (
    <SectionCard title="Repository analysis">
      <p className="text-sm text-slate-200">{analysis.summary}</p>
      <p className="mt-1 text-xs text-slate-400">Analyzed {formatDate(analysis.analyzed_at)}</p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {metrics.map(([label, value]) => (
          <div key={label} className="rounded-lg border border-slate-800 bg-slate-950 p-3">
            <p className="text-xs text-slate-400">{label}</p>
            <p className="mt-1 text-xl font-semibold text-white">{value}</p>
          </div>
        ))}
      </div>
      <div className="mt-4 space-y-3">
        {analysis.findings.map((finding) => (
          <div key={`${finding.category}-${finding.title}`} className="rounded-lg border border-slate-800 bg-slate-950 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h4 className="font-medium text-slate-100">{finding.title}</h4>
              <span className={`rounded-full border px-2 py-1 text-xs font-medium ${severityStyles[finding.severity]}`}>
                {finding.severity}
              </span>
            </div>
            <p className="mt-2 text-sm text-slate-300">{finding.description}</p>
            <p className="mt-2 text-xs text-slate-500">{finding.category}: {finding.evidence}</p>
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

export function GitHubRepositoryPage({ owner, repo, onNavigate }: GitHubRepositoryPageProps) {
  const [ownerInput, setOwnerInput] = useState(owner ?? '');
  const [repoInput, setRepoInput] = useState(repo ?? '');
  const [repository, setRepository] = useState<Repository | null>(null);
  const [commits, setCommits] = useState<Commit[]>([]);
  const [pullRequests, setPullRequests] = useState<PullRequest[]>([]);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [contents, setContents] = useState<RepositoryContent[]>([]);
  const [issueState, setIssueState] = useState<'open' | 'closed' | 'all'>(defaultIssueState);
  const [prState, setPrState] = useState<'open' | 'closed' | 'all'>(defaultPullRequestState);
  const [isLoading, setIsLoading] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState<RepositoryAnalysis | null>(null);
  const [error, setError] = useState('');
  const [analysisError, setAnalysisError] = useState('');
  const requestSequence = useRef(0);

  const repositoryId = useMemo(() => `${(owner ?? '').trim()}/${(repo ?? '').trim()}`.trim(), [owner, repo]);

  const fetchRepositoryData = async (nextOwner: string, nextRepo: string) => {
    const trimmedOwner = nextOwner.trim();
    const trimmedRepo = nextRepo.trim();
    if (!trimmedOwner || !trimmedRepo) {
      setError('Owner and repository are required.');
      return;
    }

    setIsLoading(true);
    setError('');
    const requestId = ++requestSequence.current;

    try {
      const [repoData, commitData, prData, issueData, contentsData] = await Promise.all([
        getRepository(trimmedOwner, trimmedRepo),
        getCommits(trimmedOwner, trimmedRepo, 1, 10),
        getPullRequests(trimmedOwner, trimmedRepo, prState, 1, 10),
        getIssues(trimmedOwner, trimmedRepo, issueState, 1, 10),
        getContents(trimmedOwner, trimmedRepo, 1, 30),
      ]);

      if (requestId !== requestSequence.current) return;
      setRepository(repoData);
      setCommits(commitData);
      setPullRequests(prData);
      setIssues(issueData);
      setContents(contentsData);
    } catch (loadError) {
      if (requestId !== requestSequence.current) return;
      const message = loadError instanceof Error ? loadError.message : 'Unable to load repository data.';
      setError(message);
    } finally {
      if (requestId === requestSequence.current) setIsLoading(false);
    }
  };

  useEffect(() => {
    if (!owner || !repo) {
      setRepository(null);
      setCommits([]);
      setPullRequests([]);
      setIssues([]);
      setContents([]);
      return;
    }

    fetchRepositoryData(owner, repo);
  }, [owner, repo, issueState, prState]);

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedOwner = ownerInput.trim();
    const trimmedRepo = repoInput.trim();

    if (!trimmedOwner || !trimmedRepo) {
      setError('Owner and repository are required.');
      return;
    }

    onNavigate(`/repositories/${trimmedOwner}/${trimmedRepo}`);
  };

  const handleAnalysis = async () => {
    const trimmedOwner = (owner ?? '').trim();
    const trimmedRepo = (repo ?? '').trim();
    if (!trimmedOwner || !trimmedRepo) return;

    setIsAnalyzing(true);
    setAnalysisError('');
    try {
      setAnalysis(await analyzeRepository(trimmedOwner, trimmedRepo));
    } catch (analysisLoadError) {
      const message = analysisLoadError instanceof Error ? analysisLoadError.message : 'Repository analysis failed.';
      setAnalysisError(`Repository analysis failed: ${message}`);
    } finally {
      setIsAnalyzing(false);
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <form onSubmit={handleSubmit} className="rounded-xl border border-slate-800 bg-slate-900 p-5 shadow-lg shadow-slate-950/30">
        <div className="flex flex-col gap-4 md:flex-row md:items-end">
          <div className="flex-1">
            <label htmlFor="owner" className="mb-2 block text-sm font-medium text-slate-200">
              Owner
            </label>
            <input
              id="owner"
              value={ownerInput}
              onChange={(event) => setOwnerInput(event.target.value)}
              placeholder="microsoft"
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none ring-0 transition focus:border-cyan-500"
            />
          </div>
          <div className="flex-1">
            <label htmlFor="repo" className="mb-2 block text-sm font-medium text-slate-200">
              Repository
            </label>
            <input
              id="repo"
              value={repoInput}
              onChange={(event) => setRepoInput(event.target.value)}
              placeholder="vscode"
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none ring-0 transition focus:border-cyan-500"
            />
          </div>
          <button
            type="submit"
            className="rounded-lg bg-cyan-500 px-4 py-2.5 text-sm font-medium text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={isLoading}
          >
            {isLoading ? 'Loading...' : 'Connect Repository'}
          </button>
        </div>
      </form>

      {!repositoryId ? (
        <div className="rounded-xl border border-dashed border-slate-700 bg-slate-900 p-6 text-sm text-slate-400">
          Enter a GitHub repository to fetch metadata, commits, pull requests, issues, and contents.
        </div>
      ) : null}

      {error ? (
        <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 p-4 text-sm text-rose-200">
          {error}
        </div>
      ) : null}

      {isLoading ? (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-sm text-slate-300">Loading repository...</div>
      ) : null}

      {!isLoading && repository ? (
        <>
          <RepositoryHeader repository={repository} />
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleAnalysis}
              disabled={isAnalyzing}
              className="rounded-lg bg-emerald-500 px-4 py-2.5 text-sm font-medium text-slate-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isAnalyzing ? 'Analyzing...' : 'Run Analysis'}
            </button>
            {analysis ? <span className="text-sm text-emerald-300">Analysis completed</span> : null}
          </div>
          {analysisError ? (
            <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 p-4 text-sm text-rose-200">{analysisError}</div>
          ) : null}
          {isAnalyzing ? (
            <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-sm text-slate-300">Analyzing repository...</div>
          ) : null}
          {!isAnalyzing && analysis ? <AnalysisResults analysis={analysis} /> : null}
          <RepositoryStats repository={repository} />
          <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
            <div className="space-y-6">
              <RepositoryMetadata repository={repository} />
              <SectionCard title="Recent commits">
                <CommitList commits={commits} />
              </SectionCard>
              <PullRequestList pullRequests={pullRequests} state={prState} onStateChange={setPrState} />
              <IssueList issues={issues} state={issueState} onStateChange={setIssueState} />
            </div>
            <div className="space-y-6">
              <SectionCard title="Repository contents">
                <ContentList contents={contents} />
              </SectionCard>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
