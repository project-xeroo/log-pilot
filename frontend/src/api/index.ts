import api from "./client";
import type {
  IncidentReport,
  IncidentOutcome,
  DeploymentSnapshot,
  DeploymentComparison,
  ForecastWeight,
  PaginatedResponse,
  TokenResponse,
  User,
  // Phase 3
  FleetHealth,
  ServiceHealthState,
  DedupError,
  ErrorCluster,
  AnomalyEvent,
  DeploymentRegression,
  RCAResult,
} from "@/types";

// ── Auth ──────────────────────────────────────────────────────────────────
export async function login(email: string, password: string): Promise<TokenResponse> {
  const form = new URLSearchParams({ username: email, password });
  const { data } = await api.post<TokenResponse>("/auth/token", form, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  return data;
}

export async function getMe(): Promise<User> {
  const { data } = await api.get<User>("/auth/me");
  return data;
}

// ── Reports ───────────────────────────────────────────────────────────────
export interface GenerateReportPayload {
  incident_id: string;
  title: string;
  severity?: string;
  started_at?: string;
  resolved_at?: string;
  context_logs?: string[];
  affected_services?: string[];
}

export async function generateReport(payload: GenerateReportPayload): Promise<IncidentReport> {
  const { data } = await api.post<IncidentReport>("/reports/generate", payload);
  return data;
}

export async function listReports(params?: {
  status?: string;
  severity?: string;
  page?: number;
  page_size?: number;
}): Promise<PaginatedResponse<IncidentReport>> {
  const { data } = await api.get<PaginatedResponse<IncidentReport>>("/reports", { params });
  return data;
}

export async function getReport(id: string): Promise<IncidentReport> {
  const { data } = await api.get<IncidentReport>(`/reports/${id}`);
  return data;
}

export async function updateReport(
  id: string,
  patch: Partial<IncidentReport>
): Promise<IncidentReport> {
  const { data } = await api.patch<IncidentReport>(`/reports/${id}`, patch);
  return data;
}

export async function deleteReport(id: string): Promise<void> {
  await api.delete(`/reports/${id}`);
}

export async function exportReport(id: string, format: "pdf" | "markdown"): Promise<{ url?: string; content?: string }> {
  const { data } = await api.get(`/reports/${id}/export/${format}`, { responseType: format === "pdf" ? "blob" : "json" });
  return data;
}

// ── Outcomes ──────────────────────────────────────────────────────────────
export interface CreateOutcomePayload {
  incident_id: string;
  report_id?: string;
  verdict: IncidentOutcome["verdict"];
  rca_accurate?: boolean;
  forecast_accurate?: boolean;
  time_to_detect_seconds?: number;
  time_to_resolve_seconds?: number;
  action_taken?: string;
  fired_indicators?: string[];
  forecast_score_at_incident?: number;
  notes?: string;
}

export async function createOutcome(payload: CreateOutcomePayload): Promise<IncidentOutcome> {
  const { data } = await api.post<IncidentOutcome>("/outcomes", payload);
  return data;
}

export async function listOutcomes(params?: {
  incident_id?: string;
  verdict?: string;
  page?: number;
}): Promise<PaginatedResponse<IncidentOutcome>> {
  const { data } = await api.get<PaginatedResponse<IncidentOutcome>>("/outcomes", { params });
  return data;
}

// ── Deployments ───────────────────────────────────────────────────────────
export async function listDeployments(params?: {
  service_name?: string;
  environment?: string;
  page?: number;
}): Promise<PaginatedResponse<DeploymentSnapshot>> {
  const { data } = await api.get<PaginatedResponse<DeploymentSnapshot>>("/deployments", {
    params,
  });
  return data;
}

export async function compareDeployments(
  baseId: string,
  headId: string
): Promise<DeploymentComparison> {
  const { data } = await api.get<DeploymentComparison>("/deployments/compare", {
    params: { base_id: baseId, head_id: headId },
  });
  return data;
}

// ── Forecasting weights ───────────────────────────────────────────────────
export async function listWeights(): Promise<{ items: ForecastWeight[] }> {
  const { data } = await api.get<{ items: ForecastWeight[] }>("/feedback/weights");
  return data;
}

// ── Users ─────────────────────────────────────────────────────────────────
export async function listUsers(params?: {
  page?: number;
}): Promise<PaginatedResponse<User>> {
  const { data } = await api.get<PaginatedResponse<User>>("/users", { params });
  return data;
}

export async function updateUser(
  id: string,
  patch: { role?: User["role"]; is_active?: boolean; full_name?: string }
): Promise<User> {
  const { data } = await api.patch<User>(`/users/${id}`, patch);
  return data;
}

// ── Phase 3: Analysis & Correlation Layer ─────────────────────────────────

/** Fleet health summary — all active services. */
export async function getFleetHealth(): Promise<FleetHealth> {
  const { data } = await api.get<FleetHealth>("/analysis/health");
  return data;
}

/** Single service health state. */
export async function getServiceHealth(serviceId: string): Promise<ServiceHealthState> {
  const { data } = await api.get<ServiceHealthState>(`/analysis/health/${serviceId}`);
  return data;
}

/** Deduplicated errors for a service. */
export async function listDedupErrors(
  serviceId: string,
  params?: { limit?: number; severity?: string }
): Promise<DedupError[]> {
  const { data } = await api.get<DedupError[]>(`/analysis/dedup/${serviceId}`, { params });
  return data;
}

/** Error clusters for a service. */
export async function listClusters(
  serviceId: string,
  params?: { active_only?: boolean; limit?: number }
): Promise<ErrorCluster[]> {
  const { data } = await api.get<ErrorCluster[]>(`/analysis/clusters/${serviceId}`, { params });
  return data;
}

/** List anomaly events. */
export async function listAnomalies(params?: {
  service_id?: string;
  resolved?: boolean;
  limit?: number;
}): Promise<AnomalyEvent[]> {
  const { data } = await api.get<AnomalyEvent[]>("/analysis/anomalies", { params });
  return data;
}

/** Resolve an anomaly. */
export async function resolveAnomaly(anomalyId: string, resolved_by: string): Promise<AnomalyEvent> {
  const { data } = await api.post<AnomalyEvent>(`/analysis/anomalies/${anomalyId}/resolve`, { resolved_by });
  return data;
}

/** Run RCA for a service. */
export async function runRCA(serviceId: string, window_minutes = 30): Promise<RCAResult> {
  const { data } = await api.post<RCAResult>(`/analysis/rca/${serviceId}`, { window_minutes });
  return data;
}

/** List deployment regressions. */
export async function listRegressions(params?: {
  service_id?: string;
  acknowledged?: boolean;
  limit?: number;
}): Promise<DeploymentRegression[]> {
  const { data } = await api.get<DeploymentRegression[]>("/analysis/regressions", { params });
  return data;
}

/** Acknowledge a regression. */
export async function acknowledgeRegression(
  regressionId: string,
  acknowledged_by: string
): Promise<DeploymentRegression> {
  const { data } = await api.post<DeploymentRegression>(
    `/analysis/regressions/${regressionId}/acknowledge`,
    { acknowledged_by }
  );
  return data;
}

/** Manual deployment comparison. */
export async function compareDeploymentVersions(params: {
  service_id: string;
  baseline_version: string;
  head_version: string;
  baseline_deployed_at?: string;
  head_deployed_at?: string;
  window_hours?: number;
}): Promise<DeploymentRegression[]> {
  const { data } = await api.post<DeploymentRegression[]>("/analysis/compare", params);
  return data;
}
