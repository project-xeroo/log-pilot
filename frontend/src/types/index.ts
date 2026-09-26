// Shared TypeScript types for LogPilot Phase 5

export type Role = "admin" | "developer" | "sre" | "viewer";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
}

export type ReportStatus = "draft" | "review" | "approved" | "exported";

export interface IncidentReport {
  id: string;
  title: string;
  status: ReportStatus;
  summary: string | null;
  timeline: string | null;
  affected_services: string[] | null;
  impact_analysis: string | null;
  root_cause: string | null;
  resolution: string | null;
  preventive_actions: string | null;
  incident_id: string | null;
  severity: string | null;
  started_at: string | null;
  resolved_at: string | null;
  ttd_seconds: number | null;
  ttr_seconds: number | null;
  generation_model: string | null;
  generation_duration_ms: number | null;
  author_id: string | null;
  created_at: string;
  updated_at: string;
}

export type OutcomeVerdict =
  | "true_positive"
  | "false_positive"
  | "true_negative"
  | "false_negative";

export interface IncidentOutcome {
  id: string;
  incident_id: string;
  report_id: string | null;
  verdict: OutcomeVerdict;
  rca_accurate: boolean | null;
  forecast_accurate: boolean | null;
  time_to_detect_seconds: number | null;
  time_to_resolve_seconds: number | null;
  action_taken: string | null;
  fired_indicators: string[] | null;
  forecast_score_at_incident: number | null;
  notes: string | null;
  reviewed_by_id: string | null;
}

export interface DeploymentSnapshot {
  id: string;
  service_name: string;
  environment: string;
  version: string;
  deployed_by: string | null;
  deployed_at: string;
  config_snapshot: Record<string, unknown> | null;
  created_at: string;
}

export interface DeploymentComparison {
  base: DeploymentSnapshot;
  head: DeploymentSnapshot;
  config_diff: Record<string, { base: unknown; head: unknown }>;
  version_changed: boolean;
  deployer_changed: boolean;
  time_between_seconds: number;
}

export interface ForecastWeight {
  indicator_name: string;
  weight: number;
  precision: number;
  recall: number;
  total_fired: number;
  true_positive_count: number;
  false_positive_count: number;
  false_negative_count: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  role: Role;
  user_id: string;
  email: string;
}
