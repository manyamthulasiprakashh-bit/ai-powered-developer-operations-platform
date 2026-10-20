import React, { useEffect, useMemo, useState } from 'react';
import ReactDOM from 'react-dom/client';
import { DashboardPage } from './components/DashboardPage';
import { DocumentReviewPage } from './components/documents/DocumentReviewPage';
import { DocumentsPage } from './components/documents/DocumentsPage';
import { GitHubRepositoryPage } from './components/GitHubRepositoryPage';
import './styles.css';

function App() {
  const [route, setRoute] = useState<string>('/');
  const [documentsRefreshToken, setDocumentsRefreshToken] = useState(0);

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
    if (route === '/documents') {
      return { kind: 'documents' as const };
    }
    const documentMatch = route.match(/^\/documents\/(\d+)$/);
    if (documentMatch) {
      return { kind: 'document' as const, documentId: Number(documentMatch[1]) };
    }
    const match = route.match(/^\/repositories\/([^/]+)\/([^/]+)$/);
    if (match) {
      return { kind: 'repo' as const, owner: match[1], repo: match[2] };
    }
    return { kind: 'dashboard' as const };
  }, [route]);

  const markDocumentsChanged = () => setDocumentsRefreshToken((token) => token + 1);

  if (routeInfo.kind === 'repo') {
    return <GitHubRepositoryPage owner={routeInfo.owner} repo={routeInfo.repo} onNavigate={navigate} />;
  }

  if (routeInfo.kind === 'github') {
    return <GitHubRepositoryPage onNavigate={navigate} />;
  }

  if (routeInfo.kind === 'documents') {
    return (
      <DocumentsPage
        refreshToken={documentsRefreshToken}
        onDocumentsChanged={markDocumentsChanged}
        onNavigate={navigate}
      />
    );
  }

  if (routeInfo.kind === 'document') {
    return (
      <DocumentReviewPage
        documentId={routeInfo.documentId}
        onDocumentsChanged={markDocumentsChanged}
        onNavigate={navigate}
      />
    );
  }

  return <DashboardPage onNavigate={navigate} />;
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
