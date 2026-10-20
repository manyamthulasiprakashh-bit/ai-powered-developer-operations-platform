import { useEffect, useState } from 'react';
import { DOCUMENT_PAGE_SIZE, getDocuments } from '../../services/documents';
import type { DocumentListResponse } from '../../types';
import { DocumentList } from './DocumentList';
import { DocumentUploadForm } from './DocumentUploadForm';

interface DocumentsPageProps {
  refreshToken: number;
  onDocumentsChanged: () => void;
  onNavigate: (path: string) => void;
}

export function DocumentsPage({ refreshToken, onDocumentsChanged, onNavigate }: DocumentsPageProps) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<DocumentListResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    setIsLoading(true);
    setError('');
    getDocuments(DOCUMENT_PAGE_SIZE, (page - 1) * DOCUMENT_PAGE_SIZE, { signal: controller.signal })
      .then((response) => {
        if (!active) return;
        setData(response);
        if (response.total > 0 && response.items.length === 0 && page > 1) {
          setPage(Math.max(1, Math.ceil(response.total / DOCUMENT_PAGE_SIZE)));
        }
      })
      .catch((loadError: unknown) => {
        if (!active || controller.signal.aborted) return;
        setError(loadError instanceof Error ? loadError.message : 'Unable to load documents.');
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [page, refreshToken, retryToken]);

  return (
    <main className="min-h-screen bg-slate-950 px-6 py-10 text-slate-100">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="flex flex-wrap items-end justify-between gap-4 border-b border-slate-800 pb-6">
          <div>
            <p className="text-sm uppercase tracking-[0.2em] text-cyan-400">Document review</p>
            <h1 className="mt-2 text-3xl font-bold">Documents</h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-400">
              Upload source documents, run deterministic extraction, and review the latest extracted fields.
            </p>
          </div>
          <button
            type="button"
            onClick={() => onNavigate('/')}
            className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-500"
          >
            Dashboard
          </button>
        </header>

        <DocumentUploadForm
          onUploaded={() => {
            setPage(1);
            onDocumentsChanged();
          }}
        />

        <DocumentList
          documents={data?.items ?? []}
          total={data?.total ?? 0}
          page={page}
          pageSize={DOCUMENT_PAGE_SIZE}
          isLoading={isLoading}
          error={error}
          onPageChange={setPage}
          onRetry={() => setRetryToken((token) => token + 1)}
          onOpen={(documentId) => onNavigate(`/documents/${documentId}`)}
        />
      </div>
    </main>
  );
}
