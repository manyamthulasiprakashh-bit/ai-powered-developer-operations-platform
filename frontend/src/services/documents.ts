import { API_BASE_URL } from '../config';
import type {
  DecisionDetail,
  DecisionKind,
  DecisionRequest,
  DocumentDetail,
  DocumentIntakeResponse,
  DocumentListResponse,
  ExtractedField,
  ExtractionDetail,
  FieldCorrection,
} from '../types';
import { fetchJson } from './api';

export const DOCUMENT_PAGE_SIZE = 10;
export const DOCUMENT_MAX_SIZE_BYTES = 1_048_576;
export const DOCUMENT_MAX_TEXT_CHARS = 20_000;
export const DOCUMENT_ALLOWED_EXTENSIONS = ['.txt', '.md'] as const;

const ALLOWED_CONTENT_TYPES = new Set(['text/plain', 'text/markdown']);

export interface CorrectionDraft {
  correctedValue: string;
  note: string;
}

export type CorrectionDrafts = Record<string, CorrectionDraft>;

function extensionOf(filename: string): string {
  const dot = filename.lastIndexOf('.');
  return dot >= 0 ? filename.slice(dot).toLowerCase() : '';
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDocumentDate(value: string | null): string {
  if (!value) return 'N/A';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'N/A' : date.toLocaleString();
}

export function validateDocumentFile(file: Pick<File, 'name' | 'size' | 'type'>): string | null {
  if (!file.name.trim()) return 'Choose a .txt or .md file.';
  if (!DOCUMENT_ALLOWED_EXTENSIONS.includes(extensionOf(file.name) as (typeof DOCUMENT_ALLOWED_EXTENSIONS)[number])) {
    return 'Only .txt and .md files are supported.';
  }
  if (file.size <= 0) return 'The selected file is empty.';
  if (file.size > DOCUMENT_MAX_SIZE_BYTES) {
    return `Files must be ${formatBytes(DOCUMENT_MAX_SIZE_BYTES)} or smaller.`;
  }
  const contentType = file.type.split(';')[0].trim().toLowerCase();
  if (contentType && !ALLOWED_CONTENT_TYPES.has(contentType)) {
    return 'Only plain text and Markdown files are supported.';
  }
  return null;
}

export function canDecideDocument(document: DocumentDetail): boolean {
  return (
    document.status === 'extracted' &&
    document.extraction?.status === 'succeeded' &&
    document.decision === null
  );
}

export function validateDecisionInput(decision: DecisionKind, reason: string): string | null {
  if (decision === 'reject' && !reason.trim()) {
    return 'A non-empty reason is required when rejecting a document.';
  }
  return null;
}

export function buildCorrections(
  fields: ExtractedField[],
  drafts: CorrectionDrafts,
): FieldCorrection[] {
  return fields.flatMap((field) => {
    const draft = drafts[field.name];
    if (!draft) return [];
    const correctedValue = draft.correctedValue.trim();
    const note = draft.note.trim();
    if (!correctedValue) return [];
    return [
      {
        name: field.name,
        corrected_value: correctedValue,
        note: note || null,
      },
    ];
  });
}

export function buildDecisionRequest(
  decision: DecisionKind,
  fields: ExtractedField[],
  drafts: CorrectionDrafts,
  reason: string,
): DecisionRequest {
  return {
    decision,
    corrections: buildCorrections(fields, drafts),
    reason: reason.trim() || null,
  };
}

export async function getDocuments(
  limit = DOCUMENT_PAGE_SIZE,
  offset = 0,
  init?: RequestInit,
): Promise<DocumentListResponse> {
  const url = `${API_BASE_URL}/api/documents?limit=${limit}&offset=${offset}`;
  return fetchJson<DocumentListResponse>(url, init);
}

export async function getDocument(
  documentId: number,
  init?: RequestInit,
): Promise<DocumentDetail> {
  const url = `${API_BASE_URL}/api/documents/${encodeURIComponent(String(documentId))}`;
  return fetchJson<DocumentDetail>(url, init);
}

export async function uploadDocument(
  file: File,
  init?: RequestInit,
): Promise<DocumentIntakeResponse> {
  const formData = new FormData();
  formData.append('file', file);
  return fetchJson<DocumentIntakeResponse>(`${API_BASE_URL}/api/documents`, {
    ...init,
    method: 'POST',
    body: formData,
  });
}

export async function runDocumentExtraction(
  documentId: number,
  init?: RequestInit,
): Promise<ExtractionDetail> {
  const url = `${API_BASE_URL}/api/documents/${encodeURIComponent(String(documentId))}/extractions`;
  return fetchJson<ExtractionDetail>(url, {
    ...init,
    method: 'POST',
  });
}

export async function submitDocumentDecision(
  documentId: number,
  payload: DecisionRequest,
  init?: RequestInit,
): Promise<DecisionDetail> {
  const url = `${API_BASE_URL}/api/documents/${encodeURIComponent(String(documentId))}/decisions`;
  return fetchJson<DecisionDetail>(url, {
    ...init,
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
