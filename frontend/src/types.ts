export interface Repository {
  name: string;
  full_name: string;
  owner: string;
  description: string | null;
  private: boolean;
  default_branch: string;
  language: string | null;
  stars: number;
  forks: number;
  open_issues: number;
  html_url: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface Commit {
  sha: string;
  short_sha: string;
  message: string;
  author: string | null;
  author_email: string | null;
  committed_at: string | null;
  url: string | null;
}

export interface PullRequest {
  number: number;
  title: string;
  state: string;
  author: string | null;
  created_at: string | null;
  updated_at: string | null;
  merged_at: string | null;
  url: string | null;
}

export interface Issue {
  number: number;
  title: string;
  state: string;
  author: string | null;
  labels: string[];
  created_at: string | null;
  updated_at: string | null;
  url: string | null;
}

export interface RepositoryContent {
  name: string;
  path: string;
  type: 'file' | 'dir' | string;
  size: number | null;
  url: string | null;
}

export type AnalysisSeverity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO';

export interface AnalysisFinding {
  title: string;
  description: string;
  severity: AnalysisSeverity;
  category: string;
  evidence: string;
}

export interface RepositoryAnalysis {
  owner: string;
  repository: string;
  analyzed_at: string;
  summary: string;
  metrics: {
    commit_count: number;
    open_issue_count: number;
    open_pull_request_count: number;
    root_content_count: number;
    has_readme: boolean;
    has_ci_configuration: boolean;
  };
  findings: AnalysisFinding[];
}

export interface AnalysisListItem {
  id: number;
  owner: string;
  repository: string;
  analyzed_at: string;
  summary: string;
  created_at: string;
}

export interface AnalysisListResponse {
  items: AnalysisListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface AnalysisStatistics {
  total_analyses: number;
  distinct_owners: number;
  distinct_repositories: number;
  analyses_last_7_days: number;
  analyses_last_30_days: number;
  latest_analyzed_at: string | null;
}

export type DocumentStatus =
  | 'received'
  | 'extracting'
  | 'extracted'
  | 'extraction_failed'
  | 'approved'
  | 'rejected';

export interface DocumentSummary {
  id: number;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  status: DocumentStatus;
  received_at: string;
  updated_at: string;
}

export interface DocumentListResponse {
  items: DocumentSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface FieldEvidence {
  source_quote: string;
  char_start: number | null;
  char_end: number | null;
  page: number | null;
}

export interface ExtractedField {
  name: string;
  value: string | null;
  confidence: number;
  evidence: FieldEvidence | null;
}

export interface ExtractionDetail {
  id: number;
  document_id: number;
  provider: 'deterministic' | 'openai';
  model: string | null;
  status: 'succeeded' | 'failed';
  fields: ExtractedField[];
  warnings: string[];
  created_at: string;
}

export interface FieldCorrection {
  name: string;
  corrected_value: string | null;
  note: string | null;
}

export type DecisionKind = 'approve' | 'reject';
export type DecisionOutcome = 'approved' | 'rejected';

export interface DecisionRequest {
  decision: DecisionKind;
  corrections: FieldCorrection[];
  reason: string | null;
}

export interface DecisionDetail {
  id: number;
  document_id: number;
  extraction_id: number;
  decision: DecisionOutcome;
  corrections: FieldCorrection[];
  reason: string | null;
  actor: string;
  decided_at: string;
}

export interface AuditEvent {
  id: number;
  document_id: number;
  event_type:
    | 'document_received'
    | 'extraction_started'
    | 'extraction_succeeded'
    | 'extraction_failed'
    | 'fields_corrected'
    | 'decision_recorded';
  actor: string;
  data: Record<string, unknown>;
  created_at: string;
}

export interface DocumentDetail extends DocumentSummary {
  text_preview: string;
  extraction: ExtractionDetail | null;
  decision: DecisionDetail | null;
  audit: AuditEvent[];
}

export interface DocumentIntakeResponse extends DocumentSummary {
  text_preview: string;
}
