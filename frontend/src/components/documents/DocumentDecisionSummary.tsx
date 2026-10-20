import { formatDocumentDate } from '../../services/documents';
import type { DecisionDetail } from '../../types';

function humanizeFieldName(name: string): string {
  return name
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

export function DocumentDecisionSummary({ decision }: { decision: DecisionDetail }) {
  const isApproved = decision.decision === 'approved';
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 p-5 shadow-lg shadow-slate-950/30">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Final decision</h2>
          <p className="mt-1 text-sm text-slate-400">
            Recorded {formatDocumentDate(decision.decided_at)} by {decision.actor}.
          </p>
        </div>
        <span
          className={`rounded-full border px-3 py-1 text-sm font-medium ${
            isApproved
              ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
              : 'border-rose-500/40 bg-rose-500/10 text-rose-200'
          }`}
        >
          {isApproved ? 'Approved' : 'Rejected'}
        </span>
      </div>

      {decision.reason ? (
        <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950 p-4">
          <p className="text-xs uppercase tracking-wide text-slate-500">Reason</p>
          <p className="mt-1 whitespace-pre-wrap break-words text-sm text-slate-200">{decision.reason}</p>
        </div>
      ) : null}

      <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950 p-4">
        <p className="text-xs uppercase tracking-wide text-slate-500">Reviewer corrections</p>
        {decision.corrections.length ? (
          <ul className="mt-3 space-y-3">
            {decision.corrections.map((correction, index) => (
              <li key={`${correction.name}-${index}`} className="rounded-md border border-slate-800 bg-slate-900 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium text-slate-100">{humanizeFieldName(correction.name)}</p>
                  <span className="text-xs text-slate-500">{correction.name}</span>
                </div>
                <p className="mt-2 whitespace-pre-wrap break-words text-sm text-slate-200">
                  {correction.corrected_value ?? <span className="italic text-slate-400">Cleared value</span>}
                </p>
                {correction.note ? <p className="mt-1 text-xs text-slate-400">{correction.note}</p> : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-slate-400">No field corrections were recorded.</p>
        )}
        <p className="mt-3 text-xs text-slate-500">
          These corrections are part of the decision record. The original extraction remains unchanged.
        </p>
      </div>
    </section>
  );
}
