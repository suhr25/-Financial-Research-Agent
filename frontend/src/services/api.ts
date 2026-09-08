export type ResearchStatus = string;

export interface CompanyEntity {
  name: string;
  ticker?: string | null;
  cik?: string | null;
  resolved?: boolean;
}

export interface ResearchPlan {
  raw_query: string;
  companies: CompanyEntity[];
  period?: string | null;
  requested_metrics: string[];
  financial_questions: string[];
  qualitative_questions: string[];
  risk_questions: string[];
  is_comparison: boolean;
}

export interface ResearchRun {
  research_run_id: string;
  query: string;
  status: ResearchStatus;
  plan?: ResearchPlan | null;
  created_at: string;
  updated_at: string;
  followup_iterations_used: number;
  research_queries_used: number;
  error?: string | null;
}

export interface EvidenceSpan {
  source_id: string;
  start_char: number;
  end_char: number;
  evidence_text: string;
}

export interface Claim {
  claim_id: string;
  research_run_id: string;
  claim_type: string;
  entity: string;
  metric: string;
  value: string;
  unit?: string | null;
  period?: string | null;
  basis?: string | null;
  source_id: string;
  evidence_span: EvidenceSpan;
  verification_status?: "supported" | "contradicted" | "insufficient" | string | null;
  verification_reason?: string | null;
  confidence?: number | null;
  confidence_breakdown?: Record<string, number> | null;
  statement: string;
}

export interface Source {
  source_id: string;
  title: string;
  url?: string | null;
  source_type: string;
  source_tier: string;
  publisher: string;
  retrieved_at: string;
  document_text: string;
  metadata: Record<string, unknown>;
}

export interface Conflict {
  conflict_id: string;
  entity: string;
  metric: string;
  claim_id_a: string;
  claim_id_b: string;
  source_id_a: string;
  source_id_b: string;
  value_a: string;
  value_b: string;
  reason_type: string;
  explanation: string;
  is_genuine_conflict: boolean;
}

export interface ReportSection {
  title: string;
  content: string;
  claim_ids: string[];
}

export interface ComparisonTable {
  title: string;
  columns: string[];
  rows: Record<string, unknown>[];
}

export interface Report {
  report_id: string;
  research_run_id: string;
  company_summary: string;
  executive_overview: ReportSection;
  financial_performance: ReportSection;
  key_metrics: ReportSection;
  risks: ReportSection;
  important_findings: ReportSection;
  conflicting_information: ReportSection;
  claim_verification_summary: ReportSection;
  sources_section: ReportSection;
  comparison_tables: ComparisonTable[];
  total_claims: number;
  supported_claims: number;
  contradicted_claims: number;
  insufficient_claims: number;
  average_confidence?: number | null;
}

export interface HealthResponse {
  status: string;
  demo_mode: boolean;
  llm_provider: string;
  llm_available: boolean;
  search_provider: string;
  search_available: boolean;
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof data?.detail === "string" ? data.detail : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return data as T;
}

export const api = {
  health: () => fetchJson<HealthResponse>("/api/health"),
  startResearch: (query: string) => fetchJson<ResearchRun>("/api/research", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  }),
  research: (id: string) => fetchJson<ResearchRun>(`/api/research/${id}`),
  claims: (id: string) => fetchJson<Claim[]>(`/api/research/${id}/claims`),
  sources: (id: string) => fetchJson<Source[]>(`/api/research/${id}/sources`),
  conflicts: (id: string) => fetchJson<Conflict[]>(`/api/research/${id}/conflicts`),
  report: (id: string) => fetchJson<Report>(`/api/research/${id}/report`),
};
