import { useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { ApiError } from '../../services/api';
import {
  buildCorrections,
  buildDecisionRequest,
  submitDocumentDecision,
  validateDecisionInput,
} from '../../services/documents';
import type { CorrectionDrafts } from '../../services/documents';
import type { DecisionDetail, DecisionKind, DocumentDetail, ExtractedField } from '../../types';

interface DocumentDecisionFormProps {
  document: DocumentDetail;
  fields: ExtractedField[];
  correctionDrafts: CorrectionDrafts;
  onDecisionRecorded: (decision: DecisionDetail) => void;
  onConflict: () => void;
}

export function DocumentDecisionForm({
  document,
  fields,
  correctionDrafts,
  onDecisionRecorded,
  onConflict,
}: DocumentDecisionFormProps) {
  const [decision, setDecision] = useState<DecisionKind>('approve');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [isConfirming, setIsConfirming] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const corrections = useMemo(() => buildCorrections(fields, correctionDrafts), [fields, correctionDrafts]);

  const handleReview = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (isSubmitting) return;
    const validationError = validateDecisionInput(decision, reason);
    if (validationError) {
      setError(validationError);
      return;
    }
    setError('');
    setIsConfirming(true);
  };

  const handleConfirm = async () => {
    if (isSubmitting) return;
    const validationError = validateDecisionInput(decision, reason);
    if (validationError) {
      setError(validationError);
      setIsConfirming(false);
      return;
    }

    setIsSubmitting(true);
    setError('');
    try {
      const recorded = await submitDocumentDecision(
        document.id,
        buildDecisionRequest(decision, fields, correctionDrafts, decision === 'reject' ? reason : ''),
      );
      setIsConfirming(false);
      onDecisionRecorded(recorded);
    } catch (submitError) {
      if (submitError instanceof ApiError && submitError.status === 409) {
        setError('This document is no longer decidable. The latest state has been refreshed.');
        setIsConfirming(false);
        onConflict();
      } else {
        setError(submitError instanceof Error ? submitError.message : 'Unable to record the decision.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 p-5 shadow-lg shadow-slate-950/30">
      <h2 className="text-lg font-semibold text-slate-100">Record a decision</h2>
      <p className="mt-1 text-sm text-slate-400">
        A decision is final for this document. Approving or rejecting updates the document status and appends audit
        events; it does not change the original extraction.
      </p>

      <form onSubmit={handleReview} className="mt-4 space-y-4">
        <fieldset disabled={isSubmitting || isConfirming}>
          <legend className="text-sm font-medium text-slate-200">Decision</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {(['approve', 'reject'] as const).map((option) => (
              <button
                key={option}
                type="button"
                aria-pressed={decision === option}
                onClick={() => {
                  setDecision(option);
                  setError('');
                }}
                className={`rounded-lg border px-4 py-2 text-sm font-medium transition ${
                  decision === option
                    ? option === 'approve'
                      ? 'border-emerald-500 bg-emerald-500/15 text-emerald-200'
                      : 'border-rose-500 bg-rose-500/15 text-rose-200'
                    : 'border-slate-700 bg-slate-950 text-slate-300 hover:border-slate-500'
                }`}
              >
                {option === 'approve' ? 'Approve' : 'Reject'}
              </button>
            ))}
          </div>
        </fieldset>

        {decision === 'reject' ? (
          <div>
            <label htmlFor="decision-reason" className="mb-2 block text-sm font-medium text-slate-200">
              Rejection reason <span className="text-rose-300">(required)</span>
            </label>
            <textarea
              id="decision-reason"
              value={reason}
              onChange={(event) => {
                setReason(event.target.value);
                setError('');
              }}
              disabled={isSubmitting || isConfirming}
              rows={3}
              placeholder="Explain why this document is being rejected."
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-rose-400 disabled:cursor-not-allowed disabled:opacity-60"
            />
          </div>
        ) : null}

        <div className="rounded-lg border border-slate-800 bg-slate-950 p-3 text-sm text-slate-300">
          {corrections.length
            ? `${corrections.length} proposed correction${corrections.length === 1 ? '' : 's'} will be stored with the decision.`
            : 'No field corrections proposed. The original extraction will be used as-is.'}
        </div>

        {error ? (
          <p role="alert" className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-200">
            {error}
          </p>
        ) : null}

        {!isConfirming ? (
          <button
            type="submit"
            disabled={isSubmitting}
            className="rounded-lg bg-cyan-500 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Review decision
          </button>
        ) : (
          <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4">
            <p className="text-sm font-medium text-amber-100">Confirm this decision</p>
            <p className="mt-1 text-sm text-amber-200">
              {decision === 'approve'
                ? 'Approve this document? This action cannot be repeated.'
                : 'Reject this document? This action cannot be repeated.'}
              {corrections.length ? ` ${corrections.length} correction(s) will be recorded.` : ''}
            </p>
            {decision === 'reject' ? (
              <p className="mt-2 whitespace-pre-wrap break-words text-sm text-amber-100">Reason: {reason.trim()}</p>
            ) : null}
            <div className="mt-4 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={handleConfirm}
                disabled={isSubmitting}
                className="rounded-lg bg-amber-400 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-amber-300 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isSubmitting ? 'Saving decision…' : 'Confirm decision'}
              </button>
              <button
                type="button"
                onClick={() => setIsConfirming(false)}
                disabled={isSubmitting}
                className="rounded-lg border border-amber-400/50 px-4 py-2 text-sm text-amber-100 transition hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-60"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </form>
    </section>
  );
}
