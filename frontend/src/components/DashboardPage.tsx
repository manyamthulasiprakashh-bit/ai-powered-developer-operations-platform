import { useEffect, useState } from 'react';
import { getAnalyses, getStatistics } from '../services/analyses';
import type { AnalysisListItem, AnalysisStatistics } from '../types';

interface DashboardPageProps {
  onNavigate: (path: string) => void;
}

interface DashboardData {
  analyses: AnalysisListItem[];
  statistics: AnalysisStatistics;
}

function formatDate(value: string | null): string {
  if (!value) return 'N/A';
  return new Date(value).toLocaleString();
}

function StatCard({ label, value, isLoading }: { label: string; value: string | null; isLoading: boolean }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 shadow-lg shadow-slate-950/30">
      <p className="text-sm text-slate-400">{label}</p>
      <p className="mt-3 text-3xl font-semibold">{isLoading && value === null ? 'Loading…' : value ?? '—'}</p>
    </div>
  );
}

export function DashboardPage({ onNavigate }: DashboardPageProps) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    setIsLoading(true);
    setError('');

    Promise.all([
      getAnalyses(5, 0, { signal: controller.signal }),
      getStatistics({ signal: controller.signal }),
    ])
      .then(([analysisPage, statistics]) => {
        if (!active) return;
        setData({ analyses: analysisPage.items, statistics });
      })
      .catch((loadError: unknown) => {
        if (!active || controller.signal.aborted) return;
        setError(loadError instanceof Error ? loadError.message : 'Unable to load dashboard data.');
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [reloadToken]);

  const statistics = data?.statistics ?? null;
  const analyses = data?.analyses ?? [];
  const totalAnalyses = statistics?.total_analyses ?? null;
  const isInitialLoading = isLoading && data === null;
  const isEmpty = !isLoading && !error && totalAnalyses === 0;

  const statusPill = error
    ? { label: 'Data unavailable', className: 'border-rose-500/40 bg-rose-500/10 text-rose-300' }
    : isInitialLoading
      ? { label: 'Loading', className: 'border-slate-700 bg-slate-800/60 text-slate-300' }
      : { label: 'System healthy', className: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300' };

  return (
    <main className="min-h-screen bg-slate-950 px-6 py-10 text-slate-100">
      <div className="mx-auto max-w-6xl">
        <header className="mb-8 flex items-center justify-between border-b border-slate-800 pb-6">
          <div>
            <p className="text-sm uppercase tracking-[0.2em] text-cyan-400">Platform</p>
            <h1 className="mt-2 text-3xl font-bold">AI-Powered Developer Operations</h1>
          </div>
          <div className={`rounded-full border px-3 py-1 text-sm ${statusPill.className}`}>{statusPill.label}</div>
        </header>

        {error ? (
          <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rose-500/40 bg-rose-500/10 p-4 text-sm text-rose-200">
            <span>{error}</span>
            <button
              type="button"
              onClick={() => setReloadToken((token) => token + 1)}
              className="rounded-lg border border-rose-400/50 px-3 py-1.5 font-medium text-rose-100 transition hover:bg-rose-500/20"
            >
              Retry
            </button>
          </div>
        ) : null}

        <section className="grid gap-4 md:grid-cols-4">
          <StatCard label="Total analyses" value={statistics ? statistics.total_analyses.toLocaleString() : null} isLoading={isLoading} />
          <StatCard
            label="Repositories analyzed"
            value={statistics ? statistics.distinct_repositories.toLocaleString() : null}
            isLoading={isLoading}
          />
          <StatCard
            label="Analyses (7 days)"
            value={statistics ? statistics.analyses_last_7_days.toLocaleString() : null}
            isLoading={isLoading}
          />
          <StatCard
            label="Analyses (30 days)"
            value={statistics ? statistics.analyses_last_30_days.toLocaleString() : null}
            isLoading={isLoading}
          />
        </section>

        <section className="mt-8 grid gap-6 lg:grid-cols-[1.5fr_1fr]">
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-xl font-semibold">Recent analyses</h2>
              <button
                type="button"
                onClick={() => onNavigate('/github')}
                className="rounded-lg bg-cyan-500 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-cyan-400"
              >
                Analyze a repository
              </button>
            </div>

            {isInitialLoading ? (
              <p className="text-sm text-slate-400">Loading analysis history…</p>
            ) : null}

            {isEmpty ? (
              <div className="rounded-lg border border-dashed border-slate-700 bg-slate-950 p-5 text-sm text-slate-400">
                No analyses recorded yet. Connect a repository and run your first analysis to build history.
              </div>
            ) : null}

            {!isInitialLoading && !isEmpty ? (
              <ul className="space-y-3">
                {analyses.map((analysis) => (
                  <li key={analysis.id} className="rounded-lg border border-slate-800 bg-slate-950 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <button
                        type="button"
                        onClick={() => onNavigate(`/repositories/${analysis.owner}/${analysis.repository}`)}
                        className="text-sm font-medium text-cyan-400 transition hover:text-cyan-300 hover:underline"
                      >
                        {analysis.owner}/{analysis.repository}
                      </button>
                      <span className="text-xs text-slate-400">{formatDate(analysis.analyzed_at)}</span>
                    </div>
                    <p className="mt-2 text-sm text-slate-300">{analysis.summary}</p>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
            <h2 className="mb-4 text-xl font-semibold">System health</h2>
            <ul className="space-y-3 text-sm text-slate-300">
              <li className="flex items-center justify-between border-b border-slate-800 pb-2">
                <span>API</span>
                <span className={error ? 'text-rose-400' : 'text-emerald-400'}>
                  {error ? 'Unavailable' : isInitialLoading ? 'Checking…' : 'Healthy'}
                </span>
              </li>
              <li className="flex items-center justify-between border-b border-slate-800 pb-2">
                <span>Database</span>
                <span className={error ? 'text-rose-400' : statistics ? 'text-emerald-400' : 'text-slate-400'}>
                  {error ? 'Unavailable' : statistics ? 'Connected' : 'Checking…'}
                </span>
              </li>
              <li className="flex items-center justify-between border-b border-slate-800 pb-2">
                <span>Distinct owners</span>
                <span className="text-slate-200">{statistics ? statistics.distinct_owners.toLocaleString() : '—'}</span>
              </li>
              <li className="flex items-center justify-between border-b border-slate-800 pb-2">
                <span>Latest analysis</span>
                <span className="text-slate-200">{statistics ? formatDate(statistics.latest_analyzed_at) : '—'}</span>
              </li>
              <li className="flex items-center justify-between">
                <span>AI service</span>
                <span className="text-slate-400">Optional / not configured</span>
              </li>
            </ul>
          </div>
        </section>
      </div>
    </main>
  );
}
