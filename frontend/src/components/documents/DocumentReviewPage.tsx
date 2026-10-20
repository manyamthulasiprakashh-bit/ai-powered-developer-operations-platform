import { useEffect, useState } from 'react';
import { ApiError } from '../../services/api';
import {
  canDecideDocument,
  formatBytes,
  formatDocumentDate,
  getDocument,
  runDocumentExtraction,
} from '../../services/documents';
import type { CorrectionDrafts } from '../../services/documents';
import type { DecisionDetail, DocumentDetail } from '../../types';
import { DocumentDecisionForm } from './DocumentDecisionForm';
import { DocumentDecisionSummary } from './DocumentDecisionSummary';
import { DocumentExtractionPanel } from './DocumentExtractionPanel';
import { DocumentStatusBadge } from './DocumentStatusBadge';

interface DocumentReviewPageProps {
  documentId: number;
  onDocumentsChanged: () => void;
  onNavigate: (path: string) => void;
}

function statusGuidance(document: DocumentDetail): string | null {
  if (document.decision || document.status === 'approved' || document.status === 'rejected') {
    return null;
  }
  if (document.status === 'received') {
    return 'Run deterministic extraction to prepare this document for review.';
  }
  if (document.status === 'extracting') {
    return 'Extraction is currently in progress. Refresh in a moment to see the result.';
  }
  if (document.status === 'extraction_failed') {
    return 'The latest extraction failed. Retry extraction before recording a decision.';
  }
  if (document.status === 'extracted' && document.extraction?.status !== 'succeeded') {
    return 'A successful extraction is required before a decision can be recorded.';
  }
  return null;
}

export function DocumentReviewPage({ documentId, onDocumentsChanged, onNavigate }: DocumentReviewPageProps) {
  const [document, setDocument] = useState<DocumentDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [notFound, setNotFound] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const [correctionDrafts, setCorrectionDrafts] = useState<CorrectionDrafts>({});
  const [isExtracting, setIsExtracting] = useState(false);
  const [extractionError, setExtractionError] = useState('');
  const [conflictMessage, setConflictMessage] = useState('');

  useEffect(() => {
    setDocument(null);
    setNotFound(false);
    setCorrectionDrafts({});
    setConflictMessage('');
  }, [documentId]);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    setIsLoading(true);
    setError('');
    setNotFound(false);
    getDocument(documentId, { signal: controller.signal })
      .then((loaded) => {
        if (!active) return;
        setDocument(loaded);
      })
      .catch((loadError: unknown) => {
        if (!active || controller.signal.aborted) return;
        if (loadError instanceof ApiError && loadError.status === 404) {
          setDocument(null);
          setNotFound(true);
          return;
        }
        setError(loadError instanceof Error ? loadError.message : 'Unable to load the document.');
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [documentId, reloadToken]);

  const reload = () => setReloadToken((token) => token + 1);

  const handleCorrectionChange = (fieldName: string, draft: { correctedValue: string; note: string }) => {
    setCorrectionDrafts((current) => ({ ...current, [fieldName]: draft }));
  };

  const handleDecisionRecorded = (decision: DecisionDetail) => {
    setDocument((current) =>
      current
        ? {
            ...current,
            status: decision.decision,
            decision,
            updated_at: decision.decided_at,
          }
        : current,
    );
    setCorrectionDrafts({});
    onDocumentsChanged();
    reload();
  };

  const handleConflict = () => {
    setConflictMessage('This document is no longer decidable. The latest state has been refreshed.');
    onDocumentsChanged();
    reload();
  };

  const handleExtraction = async () => {
    if (!document || isExtracting) return;
    setIsExtracting(true);
    setExtractionError('');
    try {
      await runDocumentExtraction(document.id);
      onDocumentsChanged();
      reload();
    } catch (extractError) {
      setExtractionError(extractError instanceof Error ? extractError.message : 'Unable to run extraction.');
      if (extractError instanceof ApiError && extractError.status === 409) {
        onDocumentsChanged();
        reload();
      }
    } finally {
      setIsExtracting(false);
    }
  };

  if (isLoading && !document && !notFound) {
    return (
      <main className="min-h-screen bg-slate-950 px-6 py-10 text-slate-100">
        <div className="mx-auto max-w-6xl">
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-sm text-slate-300" role="status">
            Loading document review…
          </div>
        </div>
      </main>
    );
  }

  if (notFound) {
    return (
      <main className="min-h-screen bg-slate-950 px-6 py-10 text-slate-100">
        <div className="mx-auto max-w-3xl rounded-xl border border-slate-800 bg-slate-900 p-6">
          <h1 className="text-2xl font-semibold">Document not found</h1>
          <p className="mt-2 text-sm text-slate-400">The document may have been removed or the link is incorrect.</p>
          <button
            type="button"
            onClick={() => onNavigate('/documents')}
            className="mt-5 rounded-lg bg-cyan-500 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-cyan-400"
          >
            Back to documents
          </button>
        </div>
      </main>
    );
  }

  if (!document) {
    return (
      <main className="min-h-screen bg-slate-950 px-6 py-10 text-slate-100">
        <div className="mx-auto max-w-3xl rounded-xl border border-rose-500/40 bg-rose-500/10 p-6 text-sm text-rose-200">
          <p>{error || 'Unable to load the document.'}</p>
          <button
            type="button"
            onClick={reload}
            className="mt-4 rounded-lg border border-rose-400/50 px-3 py-1.5 font-medium text-rose-100 transition hover:bg-rose-500/20"
          >
            Retry
          </button>
        </div>
      </main>
    );
  }

  const canDecide = canDecideDocument(document);
  const guidance = statusGuidance(document);
  const canRunExtraction =
    document.status !== 'approved' &&
    document.status !== 'rejected' &&
    document.status !== 'extracting' &&
    !(document.status === 'extracted' && document.extraction?.status === 'succeeded');
  const fields = document.extraction?.fields ?? [];

  return (
    <main className="min-h-screen bg-slate-950 px-6 py-10 text-slate-100">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="flex flex-wrap items-end justify-between gap-4 border-b border-slate-800 pb-6">
          <div className="min-w-0">
            <button
              type="button"
              onClick={() => onNavigate('/documents')}
              className="text-sm text-cyan-300 transition hover:text-cyan-200 hover:underline"
            >
              ← Back to documents
            </button>
            <p className="mt-4 text-sm uppercase tracking-[0.2em] text-cyan-400">Document review</p>
            <h1 className="mt-2 break-words text-3xl font-bold">{document.filename}</h1>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <DocumentStatusBadge status={document.status} />
              <span className="text-sm text-slate-400">Uploaded {formatDocumentDate(document.received_at)}</span>
            </div>
          </div>
          <button
            type="button"
            onClick={reload}
            disabled={isLoading || isExtracting}
            className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isLoading ? 'Refreshing…' : 'Refresh'}
          </button>
        </header>

        {error ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rose-500/40 bg-rose-500/10 p-4 text-sm text-rose-200">
            <span>{error}</span>
            <button
              type="button"
              onClick={reload}
              className="rounded-lg border border-rose-400/50 px-3 py-1.5 font-medium text-rose-100 transition hover:bg-rose-500/20"
            >
              Retry
            </button>
          </div>
        ) : null}

        {conflictMessage ? (
          <div role="alert" className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-sm text-amber-100">
            {conflictMessage}
          </div>
        ) : null}

        <section className="grid gap-6 lg:grid-cols-[1fr_1.4fr]">
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 shadow-lg shadow-slate-950/30">
            <h2 className="text-lg font-semibold text-slate-100">Metadata</h2>
            <dl className="mt-4 space-y-3 text-sm">
              <div className="flex justify-between gap-4 border-b border-slate-800 pb-2">
                <dt className="text-slate-400">Content type</dt>
                <dd className="text-right text-slate-100">{document.content_type}</dd>
              </div>
              <div className="flex justify-between gap-4 border-b border-slate-800 pb-2">
                <dt className="text-slate-400">Size</dt>
                <dd className="text-slate-100">{formatBytes(document.size_bytes)}</dd>
              </div>
              <div className="flex justify-between gap-4 border-b border-slate-800 pb-2">
                <dt className="text-slate-400">Last updated</dt>
                <dd className="text-right text-slate-100">{formatDocumentDate(document.updated_at)}</dd>
              </div>
              <div className="flex flex-col gap-1 border-b border-slate-800 pb-2">
                <dt className="text-slate-400">SHA-256</dt>
                <dd className="break-all font-mono text-xs text-slate-300">{document.sha256}</dd>
              </div>
            </dl>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 shadow-lg shadow-slate-950/30">
            <h2 className="text-lg font-semibold text-slate-100">Bounded text preview</h2>
            <p className="mt-1 text-sm text-slate-400">
              Only a bounded preview can be shown. The complete stored document body is never returned.
            </p>
            {document.text_preview ? (
              <pre className="mt-4 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-slate-800 bg-slate-950 p-4 text-sm text-slate-200">
                {document.text_preview}
              </pre>
            ) : (
              <div className="mt-4 rounded-lg border border-dashed border-slate-700 bg-slate-950 p-4 text-sm text-slate-400">
                No preview is available. Short documents are not echoed in full; longer documents return a bounded
                prefix only.
              </div>
            )}
          </div>
        </section>

        {guidance || canRunExtraction ? (
          <section className="rounded-xl border border-slate-800 bg-slate-900 p-5 shadow-lg shadow-slate-950/30">
            <h2 className="text-lg font-semibold text-slate-100">Review readiness</h2>
            {guidance ? <p className="mt-2 text-sm text-slate-300">{guidance}</p> : null}
            {canRunExtraction ? (
              <button
                type="button"
                onClick={handleExtraction}
                disabled={isExtracting}
                className="mt-4 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isExtracting
                  ? 'Running extraction…'
                  : document.status === 'extraction_failed'
                    ? 'Retry extraction'
                    : 'Run deterministic extraction'}
              </button>
            ) : null}
            {isExtracting ? (
              <p role="status" className="mt-3 text-sm text-slate-400">
                Extracting fields locally. This can take a moment.
              </p>
            ) : null}
            {extractionError ? (
              <p role="alert" className="mt-3 rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-200">
                {extractionError}
              </p>
            ) : null}
          </section>
        ) : null}

        <DocumentExtractionPanel
          extraction={document.extraction}
          correctionDrafts={correctionDrafts}
          onCorrectionChange={handleCorrectionChange}
          showCorrections={canDecide}
          disabled={isExtracting}
        />

        {document.decision ? <DocumentDecisionSummary decision={document.decision} /> : null}

        {canDecide ? (
          <DocumentDecisionForm
            document={document}
            fields={fields}
            correctionDrafts={correctionDrafts}
            onDecisionRecorded={handleDecisionRecorded}
            onConflict={handleConflict}
          />
        ) : null}

        {!canDecide && !document.decision && document.status !== 'approved' && document.status !== 'rejected' ? (
          <section className="rounded-xl border border-slate-800 bg-slate-900 p-5 text-sm text-slate-400">
            Decision controls are unavailable until the document has a successful extraction and is ready for review.
          </section>
        ) : null}
      </div>
    </main>
  );
}
