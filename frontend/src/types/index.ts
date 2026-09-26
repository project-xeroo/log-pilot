// Shared TypeScript types matching the backend schemas

// ── Auth & RBAC (PRD §10) ───────────────────────────────────────────────────

export type Role = 'admin' | 'sre' | 'developer' | 'manager' | 'junior' | 'viewer'
/** @deprecated use Role */
export type UserRole = Role

/** Mirrors shared.models.Permission — the server is the source of truth. */
export type Permission =
  | 'logs:upload'
  | 'search:read'
  | 'chat:use'
  | 'feed:read'
  | 'report:create'
  | 'report:read'
  | 'report:update'
  | 'report:export'
  | 'report:delete'
  | 'outcome:write'
  | 'outcome:read'
  | 'deployment:read'
  | 'deployment:compare'
  | 'user:manage'
  | 'forecast:read'
  | 'alert:read'
  | 'alert:manage'

export interface User {
  id: string
  email: string
  full_name: string | null
  role: Role
  is_active?: boolean
}

/** GET /auth/me */
export interface CurrentUser extends User {
  permissions: Permission[]
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

// ── Search ──────────────────────────────────────────────────────────────────

export type SearchMode = 'keyword' | 'semantic'

export interface SearchRequest {
  query: string
  mode?: SearchMode
  service_name?: string
  environment?: string
  severity?: string[]
  deployment_version?: string
  trace_id?: string
  time_from?: string
  time_to?: string
  limit?: number
  offset?: number
}

export interface LogRecordResult {
  id: number
  timestamp: string | null
  service_name: string | null
  severity: string
  message: string | null
  environment: string | null
  deployment_version: string | null
  trace_id: string | null
  request_id: string | null
  http_method: string | null
  http_path: string | null
  http_status: number | null
  duration_ms: number | null
  log_format: string
  pii_was_redacted: boolean
  extra_fields: Record<string, unknown> | null
  similarity_score: number | null
}

export interface SearchResponse {
  query: string
  mode: SearchMode
  total: number
  results: LogRecordResult[]
  latency_ms: number
}

export interface SearchFilters {
  services: string[]
  environments: string[]
  severities: string[]
  deployment_versions: string[]
}

// ── Chat ────────────────────────────────────────────────────────────────────

export interface ChatRequest {
  question: string
  session_id?: string
  service_name?: string
  environment?: string
  time_from?: string
  time_to?: string
}

export interface CitedRecord {
  id: number
  timestamp: string | null
  service_name: string | null
  severity: string
  message: string | null
  similarity_score: number | null
}

export interface ChatResponse {
  session_id: string
  message_id: string
  answer: string
  cited_records: CitedRecord[]
  context_records_retrieved: number
  latency_ms: number
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  cited_records?: CitedRecord[]
  latency_ms?: number
  helpful?: boolean | null  // null = not yet rated
}

export interface ChatSession {
  id: string
  user_id: string | null
  created_at: string
  updated_at: string
}

// ── Feed ────────────────────────────────────────────────────────────────────

export type FeedEntryType =
  | 'anomaly_detected'
  | 'risk_score_updated'
  | 'chat_answer'
  | 'ingestion_completed'
  | 'alert_fired'
  | 'report_drafted'
  | 'agent_observation'

export interface FeedEntry {
  id: number
  created_at: string
  entry_type: FeedEntryType
  service_name: string | null
  title: string
  body: string | null
  severity: string | null
  risk_score: number | null
  source_session_id: string | null
  source_chat_message_id: string | null
  metadata: Record<string, unknown> | null
  is_read: boolean
}

export interface FeedResponse {
  entries: FeedEntry[]
  total: number
  limit: number
  offset: number
}

// ── Reporting & feedback (Phase 5) ──────────────────────────────────────────

export type ReportStatus = 'draft' | 'review' | 'approved' | 'exported'

export interface IncidentReport {
  id: string
  title: string
  status: ReportStatus
  summary: string | null
  timeline: string | null
  affected_services: string[] | null
  impact_analysis: string | null
  root_cause: string | null
  resolution: string | null
  preventive_actions: string | null
  incident_id: string | null
  severity: string | null
  started_at: string | null
  resolved_at: string | null
  ttd_seconds: number | null
  ttr_seconds: number | null
  generation_model: string | null
  generation_duration_ms: number | null
  author_id: string | null
  created_at: string
  updated_at: string
}

export type OutcomeVerdict =
  | 'true_positive'
  | 'false_positive'
  | 'true_negative'
  | 'false_negative'

export interface IncidentOutcome {
  id: string
  incident_id: string
  report_id: string | null
  alert_id: string | null
  verdict: OutcomeVerdict
  rca_accurate: boolean | null
  forecast_accurate: boolean | null
  time_to_detect_seconds: number | null
  time_to_resolve_seconds: number | null
  action_taken: string | null
  fired_indicators: string[] | null
  forecast_score_at_incident: number | null
  notes: string | null
  reviewed_by_id: string | null
}

export interface DeploymentSnapshot {
  id: string
  service_name: string
  environment: string
  version: string
  deployed_by: string | null
  deployed_at: string
  config_snapshot: Record<string, unknown> | null
  created_at: string
}

export interface DeploymentComparison {
  base: DeploymentSnapshot
  head: DeploymentSnapshot
  config_diff: Record<string, { base: unknown; head: unknown }>
  version_changed: boolean
  deployer_changed: boolean
  time_between_seconds: number
}

export interface ForecastWeight {
  indicator_name: string
  weight: number
  precision: number
  recall: number
  total_fired: number
  true_positive_count: number
  false_positive_count: number
  false_negative_count: number
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

// ── Analysis & correlation (Phase 3) ────────────────────────────────────────

export interface ServiceHealthState {
  service_id: string
  service_name: string | null
  health_score: number
  baseline_error_rate: number
  current_error_rate: number
  baseline_deviation_z: number
  active_cluster_count: number
  total_deduped_error_count: number
  open_anomaly_count: number
  top_cluster_label: string | null
  latest_risk_tier: 'normal' | 'warning' | 'critical'
  latest_risk_score: number
  evaluated_at: string
}

export interface FleetHealth {
  total_services: number
  healthy_count: number
  warning_count: number
  critical_count: number
  total_open_anomalies: number
  total_active_clusters: number
  most_at_risk_service: string | null
  evaluated_at: string
  services: ServiceHealthState[]
}

export interface DedupError {
  id: string
  service_id: string
  fingerprint: string
  canonical_message: string
  severity: string
  occurrence_count: number
  first_seen: string
  last_seen: string
  cluster_id: string | null
}

export interface ErrorCluster {
  id: string
  service_id: string
  cluster_label: number
  auto_label: string | null
  confidence_score: number
  member_count: number
  is_active: boolean
  first_seen: string
  last_seen: string
}

export type AnomalyType =
  | 'spike'
  | 'new_error_type'
  | 'service_silence'
  | 'cluster_drift'

export interface AnomalyEvent {
  id: string
  service_id: string
  cluster_id: string | null
  anomaly_type: AnomalyType
  explanation: string
  z_score: number | null
  observed_value: number | null
  baseline_mean: number | null
  baseline_std: number | null
  severity: 'warning' | 'critical'
  detected_at: string
  resolved_at: string | null
  is_resolved: boolean
  context: Record<string, unknown> | null
}

export interface DeploymentRegression {
  id: string
  service_id: string
  baseline_version: string
  head_version: string
  regression_type: string
  explanation: string
  baseline_error_rate: number | null
  head_error_rate: number | null
  error_rate_delta: number | null
  cluster_id: string | null
  confidence: number | null
  detected_at: string
  acknowledged: boolean
  acknowledged_by: string | null
  acknowledged_at: string | null
}

export interface CausalStep {
  order: number
  service: string
  event_type: string
  timestamp: string
  description: string
  supporting_log_ids: string[]
  confidence: number
}

export interface RCAResult {
  service_name: string
  window_start: string
  window_end: string
  root_cause_summary: string
  causal_chain: CausalStep[]
  affected_services: string[]
  confidence_score: number
  ai_model: string
  duration_ms: number
  supporting_evidence: Record<string, unknown>[]
}

// ── WebSocket ────────────────────────────────────────────────────────────────

/** Payload of an alert_event (relayed from the notification service). */
export interface AlertEventData {
  alert_id: string
  service_name: string
  risk_tier: 'warning' | 'critical' | string
}

export type WsMessage =
  | { type: 'ping' }
  | { type: 'pong' }
  | { type: 'feed_event'; data: FeedEntry }
  | { type: 'alert_event'; data: AlertEventData }
