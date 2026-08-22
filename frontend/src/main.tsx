import React, { useEffect, useMemo, useState } from 'react';
import ReactDOM from 'react-dom/client';
import { GitHubRepositoryPage } from './components/GitHubRepositoryPage';
import './styles.css';

function DashboardPage({ onNavigate }: { onNavigate: (path: string) => void }) {
  return (
    <main className="min-h-screen bg-slate-950 px-6 py-10 text-slate-100">
      <div className="mx-auto max-w-6xl">
        <header className="mb-8 flex items-center justify-between border-b border-slate-800 pb-6">
          <div>
            <p className="text-sm uppercase tracking-[0.2em] text-cyan-400">Platform</p>
            <h1 className="mt-2 text-3xl font-bold">AI-Powered Developer Operations</h1>
          </div>
          <div className="rounded-full border border-emerald-500/40 bg-emerald-500/10 px-3 py-1 text-sm text-emerald-300">
            System healthy
          </div>
        </header>

        <section className="grid gap-4 md:grid-cols-4">
          {[
            ['Connected repositories', '1'],
            ['Total analyses', '0'],
            ['Detected issues', '0'],
            ['Critical issues', '0'],
          ].map(([label, value]) => (
            <div key={label} className="rounded-xl border border-slate-800 bg-slate-900 p-5 shadow-lg shadow-slate-950/30">
              <p className="text-sm text-slate-400">{label}</p>
              <p className="mt-3 text-3xl font-semibold">{value}</p>
            </div>
          ))}
        </section>

        <section className="mt-8 grid gap-6 lg:grid-cols-[1.5fr_1fr]">
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
            <h2 className="mb-4 text-xl font-semibold">Connected Repository</h2>
            <div className="rounded-lg border border-slate-800 bg-slate-950 p-4">
              <p className="text-sm text-slate-400">microsoft/vscode</p>
              <div className="mt-3 flex flex-wrap items-center gap-3 text-sm text-slate-300">
                <span>Language: TypeScript</span>
                <span>Stars: 189k+</span>
                <span>Forks: 41k+</span>
              </div>
              <button
                type="button"
                onClick={() => onNavigate('/repositories/microsoft/vscode')}
                className="mt-4 rounded-lg bg-cyan-500 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-cyan-400"
              >
                View Repository
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
            <h2 className="mb-4 text-xl font-semibold">System health</h2>
            <ul className="space-y-3 text-sm text-slate-300">
              <li className="flex items-center justify-between border-b border-slate-800 pb-2"><span>API</span><span className="text-emerald-400">Healthy</span></li>
              <li className="flex items-center justify-between border-b border-slate-800 pb-2"><span>Database</span><span className="text-yellow-400">Pending</span></li>
              <li className="flex items-center justify-between"><span>AI service</span><span className="text-slate-400">Not configured</span></li>
            </ul>
          </div>
        </section>
      </div>
    </main>
  );
}

function App() {
  const [route, setRoute] = useState<string>('/');

  useEffect(() => {
    const syncRoute = () => {
      const next = window.location.hash.replace(/^#/, '') || '/';
      setRoute(next);
    };

    syncRoute();
    window.addEventListener('hashchange', syncRoute);
    return () => window.removeEventListener('hashchange', syncRoute);
  }, []);

  const navigate = (path: string) => {
    window.location.hash = path;
  };

  const routeInfo = useMemo(() => {
    if (route === '/' || route === '') {
      return { kind: 'dashboard' as const };
    }
    if (route === '/github') {
      return { kind: 'github' as const };
    }
    const match = route.match(/^\/repositories\/([^/]+)\/([^/]+)$/);
    if (match) {
      return { kind: 'repo' as const, owner: match[1], repo: match[2] };
    }
    return { kind: 'dashboard' as const };
  }, [route]);

  if (routeInfo.kind === 'repo') {
    return <GitHubRepositoryPage owner={routeInfo.owner} repo={routeInfo.repo} onNavigate={navigate} />;
  }

  if (routeInfo.kind === 'github') {
    return <GitHubRepositoryPage onNavigate={navigate} />;
  }

  return <DashboardPage onNavigate={navigate} />;
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
