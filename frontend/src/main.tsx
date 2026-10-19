import React, { useEffect, useMemo, useState } from 'react';
import ReactDOM from 'react-dom/client';
import { DashboardPage } from './components/DashboardPage';
import { GitHubRepositoryPage } from './components/GitHubRepositoryPage';
import './styles.css';

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
