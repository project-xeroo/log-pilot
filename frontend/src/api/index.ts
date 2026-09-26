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
