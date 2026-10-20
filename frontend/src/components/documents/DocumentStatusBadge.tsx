import type { DocumentStatus } from '../../types';

const statusStyles: Record<DocumentStatus, string> = {
  received: 'border-slate-600 bg-slate-800/70 text-slate-200',
  extracting: 'border-amber-500/40 bg-amber-500/10 text-amber-200',
  extracted: 'border-cyan-500/40 bg-cyan-500/10 text-cyan-200',
  extraction_failed: 'border-rose-500/40 bg-rose-500/10 text-rose-200',
  approved: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200',
  rejected: 'border-rose-500/40 bg-rose-500/10 text-rose-200',
};

const statusLabels: Record<DocumentStatus, string> = {
  received: 'Received',
  extracting: 'Extracting',
  extracted: 'Ready for review',
  extraction_failed: 'Extraction failed',
  approved: 'Approved',
  rejected: 'Rejected',
};

export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${statusStyles[status]}`}>
      {statusLabels[status]}
    </span>
  );
}
