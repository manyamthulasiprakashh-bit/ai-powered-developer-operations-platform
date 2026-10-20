import type { CorrectionDrafts } from '../../services/documents';
import type { ExtractionDetail } from '../../types';

interface DocumentExtractionPanelProps {
  extraction: ExtractionDetail | null;
  correctionDrafts: CorrectionDrafts;
  onCorrectionChange: (fieldName: string, draft: { correctedValue: string; note: string }) => void;
  showCorrections: boolean;
  disabled: boolean;
}

function humanizeFieldName(name: string): string {
  return name
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

export function DocumentExtractionPanel({
  extraction,
  correctionDrafts,
  onCorrectionChange,
  showCorrections,
  disabled,
}: DocumentExtractionPanelProps) {
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 p-5 shadow-lg shadow-slate-950/30">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Extracted fields</h2>
          <p className="mt-1 text-sm text-slate-400">
            Original extraction values are read-only. Reviewer corrections are stored with the decision and never
            modify this extraction record.
          </p>
        </div>
        {extraction ? (
          <span className="rounded-full border border-slate-700 bg-slate-950 px-3 py-1 text-xs text-slate-300">
            {extraction.status === 'succeeded' ? 'Extraction succeeded' : 'Extraction failed'}
          </span>
        ) : null}
      </div>

      {!extraction ? (
        <div className="mt-4 rounded-lg border border-dashed border-slate-700 bg-slate-950 p-4 text-sm text-slate-400">
          No extraction has been recorded for this document yet.
        </div>
      ) : null}

      {extraction?.warnings.length ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {extraction.warnings.map((warning, index) => (
            <span
              key={`${warning}-${index}`}
              className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-1 text-xs text-amber-200"
            >
              {warning}
            </span>
          ))}
        </div>
      ) : null}

      {extraction && extraction.fields.length === 0 ? (
        <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950 p-4 text-sm text-slate-400">
          The extractor returned no fields for this document.
        </div>
      ) : null}

      {extraction && extraction.fields.length > 0 ? (
        <div className="mt-4 space-y-4">
          {extraction.fields.map((field) => {
            const draft = correctionDrafts[field.name] ?? { correctedValue: '', note: '' };
            const originalId = `original-${field.name}`;
            return (
              <article key={field.name} className="rounded-lg border border-slate-800 bg-slate-950 p-4">
                <div className="grid gap-4 lg:grid-cols-2">
                  <div>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h3 className="text-sm font-semibold text-slate-100">{humanizeFieldName(field.name)}</h3>
                      <span className="text-xs text-slate-400">
                        {Math.round(field.confidence * 100)}% confidence
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-slate-500">{field.name}</p>
                    <p id={originalId} className="mt-3 break-words rounded-md border border-slate-800 bg-slate-900 p-3 text-sm text-slate-100">
                      {field.value ?? <span className="italic text-slate-400">Not found</span>}
                    </p>
                    <p className="mt-2 text-[11px] uppercase tracking-wide text-slate-500">Original extraction</p>

                    <div className="mt-3 rounded-md border border-slate-800 bg-slate-900 p-3">
                      <p className="text-xs font-medium text-slate-300">Supporting evidence</p>
                      {field.evidence ? (
                        <>
                          <blockquote className="mt-2 whitespace-pre-wrap break-words border-l-2 border-cyan-500/60 pl-3 text-sm text-slate-300">
                            {field.evidence.source_quote}
                          </blockquote>
                          <p className="mt-2 text-xs text-slate-500">
                            {field.evidence.page != null ? `Page ${field.evidence.page}` : 'Text document'}
                            {field.evidence.char_start != null && field.evidence.char_end != null
                              ? ` · characters ${field.evidence.char_start}–${field.evidence.char_end}`
                              : ''}
                          </p>
                        </>
                      ) : (
                        <p className="mt-2 text-xs text-slate-400">No supporting quote was recorded.</p>
                      )}
                    </div>
                  </div>

                  {showCorrections ? (
                    <div className="rounded-md border border-cyan-500/20 bg-cyan-500/5 p-4">
                      <p className="text-xs font-semibold uppercase tracking-wide text-cyan-300">Proposed correction</p>
                      <label htmlFor={`correction-${field.name}`} className="mt-3 block text-xs text-slate-300">
                        Corrected value
                      </label>
                      <input
                        id={`correction-${field.name}`}
                        type="text"
                        value={draft.correctedValue}
                        disabled={disabled}
                        onChange={(event) =>
                          onCorrectionChange(field.name, { ...draft, correctedValue: event.target.value })
                        }
                        placeholder="Leave blank to keep the original"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-cyan-500 disabled:cursor-not-allowed disabled:opacity-60"
                      />
                      <label htmlFor={`note-${field.name}`} className="mt-3 block text-xs text-slate-300">
                        Reviewer note
                      </label>
                      <input
                        id={`note-${field.name}`}
                        type="text"
                        value={draft.note}
                        disabled={disabled}
                        onChange={(event) => onCorrectionChange(field.name, { ...draft, note: event.target.value })}
                        placeholder="Optional note"
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-cyan-500 disabled:cursor-not-allowed disabled:opacity-60"
                      />
                      <p className="mt-2 text-xs text-slate-500">
                        These values are saved with the decision only; the original extraction stays unchanged. A note
                        is stored only when a corrected value is entered.
                      </p>
                    </div>
                  ) : null}
                </div>
              </article>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
