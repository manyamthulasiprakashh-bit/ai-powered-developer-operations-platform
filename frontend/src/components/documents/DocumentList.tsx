import { formatBytes, formatDocumentDate } from '../../services/documents';
import type { DocumentSummary } from '../../types';
import { DocumentStatusBadge } from './DocumentStatusBadge';

interface DocumentListProps {
  documents: DocumentSummary[];
  total: number;
  page: number;
  pageSize: number;
  isLoading: boolean;
  error: string;
  onPageChange: (page: number) => void;
  onRetry: () => void;
  onOpen: (documentId: number) => void;
}

export function DocumentList({
  documents,
  total,
  page,
  pageSize,
  isLoading,
  error,
  onPageChange,
  onRetry,
  onOpen,
}: DocumentListProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 p-5 shadow-lg shadow-slate-950/30">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Documents</h2>
          <p className="mt-1 text-sm text-slate-400">
            {total.toLocaleString()} {total === 1 ? 'document' : 'documents'} stored.
          </p>
        </div>
        <span className="rounded-full border border-slate-700 bg-slate-950 px-3 py-1 text-xs text-slate-300">
          Page {page} of {totalPages}
        </span>
      </div>

      {error ? (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-rose-500/40 bg-rose-500/10 p-4 text-sm text-rose-200">
          <span>{error}</span>
          <button
            type="button"
            onClick={onRetry}
            className="rounded-lg border border-rose-400/50 px-3 py-1.5 font-medium text-rose-100 transition hover:bg-rose-500/20"
          >
            Retry
          </button>
        </div>
      ) : null}

      {isLoading && documents.length === 0 ? (
        <div className="mt-4 space-y-3" aria-label="Loading documents" role="status">
          {[0, 1, 2].map((item) => (
            <div key={item} className="h-20 animate-pulse rounded-lg border border-slate-800 bg-slate-950" />
          ))}
          <span className="sr-only">Loading documents…</span>
        </div>
      ) : null}

      {!isLoading && !error && documents.length === 0 ? (
        <div className="mt-4 rounded-lg border border-dashed border-slate-700 bg-slate-950 p-5 text-sm text-slate-400">
          No documents yet. Upload a `.txt` or `.md` file to begin the review workflow.
        </div>
      ) : null}

      {documents.length > 0 ? (
        <ul className="mt-4 space-y-3">
          {documents.map((document) => (
            <li key={document.id} className="rounded-lg border border-slate-800 bg-slate-950 p-4">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div className="min-w-0">
                  <button
                    type="button"
                    onClick={() => onOpen(document.id)}
                    className="max-w-full truncate text-left text-sm font-semibold text-cyan-300 transition hover:text-cyan-200 hover:underline"
                  >
                    {document.filename}
                  </button>
                  <p className="mt-1 text-xs text-slate-400">
                    {formatDocumentDate(document.received_at)} · {document.content_type} · {formatBytes(document.size_bytes)}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <DocumentStatusBadge status={document.status} />
                  <button
                    type="button"
                    onClick={() => onOpen(document.id)}
                    className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-200 transition hover:border-cyan-500/60 hover:text-cyan-200"
                  >
                    Open review
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="mt-5 flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={() => onPageChange(page - 1)}
          disabled={isLoading || page <= 1}
          className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-200 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Previous
        </button>
        <span className="text-xs text-slate-400">
          {documents.length ? `${(page - 1) * pageSize + 1}–${(page - 1) * pageSize + documents.length}` : '0'} of{' '}
          {total.toLocaleString()}
        </span>
        <button
          type="button"
          onClick={() => onPageChange(page + 1)}
          disabled={isLoading || page >= totalPages}
          className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-200 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Next
        </button>
      </div>
    </section>
  );
}
