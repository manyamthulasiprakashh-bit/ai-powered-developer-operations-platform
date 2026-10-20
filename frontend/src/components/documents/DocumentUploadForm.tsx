import { useRef, useState } from 'react';
import type { FormEvent } from 'react';
import {
  DOCUMENT_MAX_SIZE_BYTES,
  DOCUMENT_MAX_TEXT_CHARS,
  formatBytes,
  uploadDocument,
  validateDocumentFile,
} from '../../services/documents';
import type { DocumentIntakeResponse } from '../../types';

interface DocumentUploadFormProps {
  onUploaded: (document: DocumentIntakeResponse) => void;
}

export function DocumentUploadForm({ onUploaded }: DocumentUploadFormProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [isUploading, setIsUploading] = useState(false);

  const handleFileChange = (nextFile: File | null) => {
    setFile(nextFile);
    setError('');
    setSuccess('');
    if (!nextFile) return;
    const validationError = validateDocumentFile(nextFile);
    if (validationError) setError(validationError);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (isUploading) return;

    if (!file) {
      setError('Choose a .txt or .md file to upload.');
      return;
    }
    const validationError = validateDocumentFile(file);
    if (validationError) {
      setError(validationError);
      return;
    }

    setIsUploading(true);
    setError('');
    setSuccess('');
    try {
      const uploaded = await uploadDocument(file);
      setSuccess(`Uploaded “${uploaded.filename}”. Open it to run deterministic extraction.`);
      setFile(null);
      onUploaded(uploaded);
      if (inputRef.current) inputRef.current.value = '';
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : 'Unable to upload the document.');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 p-5 shadow-lg shadow-slate-950/30">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Upload a document</h2>
          <p className="mt-1 text-sm text-slate-400">
            Accepts UTF-8 `.txt` and `.md` files up to {formatBytes(DOCUMENT_MAX_SIZE_BYTES)} and{' '}
            {DOCUMENT_MAX_TEXT_CHARS.toLocaleString()} characters. The stored body is never displayed in full.
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="mt-4 space-y-4">
        <div>
          <label htmlFor="document-file" className="mb-2 block text-sm font-medium text-slate-200">
            Document file
          </label>
          <input
            ref={inputRef}
            id="document-file"
            type="file"
            accept=".txt,.md,text/plain,text/markdown"
            disabled={isUploading}
            onChange={(event) => handleFileChange(event.target.files?.[0] ?? null)}
            className="block w-full cursor-pointer rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 file:mr-3 file:rounded-md file:border-0 file:bg-slate-800 file:px-3 file:py-1.5 file:text-sm file:text-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
          />
          {file ? (
            <p className="mt-2 text-xs text-slate-400">
              Selected: {file.name} ({formatBytes(file.size)})
            </p>
          ) : null}
        </div>

        <button
          type="submit"
          disabled={isUploading || !file}
          className="rounded-lg bg-cyan-500 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isUploading ? 'Uploading…' : 'Upload document'}
        </button>

        {isUploading ? (
          <p role="status" className="rounded-lg border border-slate-700 bg-slate-950 p-3 text-sm text-slate-300">
            Uploading document. This can take a moment for larger files.
          </p>
        ) : null}

        {error ? (
          <p role="alert" className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-200">
            {error}
          </p>
        ) : null}

        {success ? (
          <p role="status" className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm text-emerald-200">
            {success}
          </p>
        ) : null}
      </form>
    </section>
  );
}
