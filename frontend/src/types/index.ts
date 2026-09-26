// Shared TypeScript types for LogPilot — Phase 5 + Phase 3 Analysis Layer

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

// ── Phase 3: Analysis & Correlation Layer ─────────────────────────────────

export interface ServiceHealthState {
  service_id: string;
  service_name: string | null;
  health_score: number;
  baseline_error_rate: number;
  current_error_rate: number;
  baseline_deviation_z: number;
  active_cluster_count: number;
  total_deduped_error_count: number;
  open_anomaly_count: number;
  top_cluster_label: string | null;
  latest_risk_tier: "normal" | "warning" | "critical";
  latest_risk_score: number;
  evaluated_at: string;
}

export interface FleetHealth {
  total_services: number;
  healthy_count: number;
  warning_count: number;
  critical_count: number;
  total_open_anomalies: number;
  total_active_clusters: number;
  most_at_risk_service: string | null;
  evaluated_at: string;
  services: ServiceHealthState[];
}

export interface DedupError {
  id: string;
  service_id: string;
  fingerprint: string;
  canonical_message: string;
  severity: string;
  occurrence_count: number;
  first_seen: string;
  last_seen: string;
  cluster_id: string | null;
}

export interface ErrorCluster {
  id: string;
  service_id: string;
  cluster_label: number;
  auto_label: string | null;
  confidence_score: number;
  member_count: number;
  is_active: boolean;
  first_seen: string;
  last_seen: string;
}

export type AnomalyType =
  | "spike"
  | "new_error_type"
  | "service_silence"
  | "cluster_drift";

export interface AnomalyEvent {
  id: string;
  service_id: string;
  cluster_id: string | null;
  anomaly_type: AnomalyType;
  explanation: string;
  z_score: number | null;
  observed_value: number | null;
  baseline_mean: number | null;
  baseline_std: number | null;
  severity: "warning" | "critical";
  detected_at: string;
  resolved_at: string | null;
  is_resolved: boolean;
  context: Record<string, unknown> | null;
}

export interface DeploymentRegression {
  id: string;
  service_id: string;
  baseline_version: string;
  head_version: string;
  regression_type: string;
  explanation: string;
  baseline_error_rate: number | null;
  head_error_rate: number | null;
  error_rate_delta: number | null;
  cluster_id: string | null;
  confidence: number | null;
  detected_at: string;
  acknowledged: boolean;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
}

export interface CausalStep {
  order: number;
  service: string;
  event_type: string;
  timestamp: string;
  description: string;
  supporting_log_ids: string[];
  confidence: number;
}

export interface RCAResult {
  service_name: string;
  window_start: string;
  window_end: string;
  root_cause_summary: string;
  causal_chain: CausalStep[];
  affected_services: string[];
  confidence_score: number;
  ai_model: string;
  duration_ms: number;
  supporting_evidence: Record<string, unknown>[];
}
