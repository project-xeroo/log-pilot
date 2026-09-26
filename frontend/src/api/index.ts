/**
 * Axios-based API client for all LogPilot gateway endpoints.
 *
 * Requests go to `/api/*`, which the Vite dev server and the console's nginx
 * proxy to the gateway (stripping `/api`), so API paths never collide with
 * SPA routes like /feed or /search. For CDN hosting, set VITE_API_BASE_URL
 * to the gateway origin instead.
 */
import axios from 'axios'
import type {
  AnomalyEvent,
  ChatRequest,
  ChatResponse,
  CurrentUser,
  DedupError,
  DeploymentComparison,
  DeploymentRegression,
  DeploymentSnapshot,
  ErrorCluster,
  FeedResponse,
  FleetHealth,
  ForecastWeight,
  IncidentOutcome,
  IncidentReport,
  PaginatedResponse,
  RCAResult,
  SearchFilters,
  SearchRequest,
  SearchResponse,
  ServiceHealthState,
  TokenResponse,
  User,
} from '@/types'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'
const TOKEN_KEY = 'access_token'

export const tokenStorage = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

export const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

// Attach JWT token to every request
apiClient.interceptors.request.use((config) => {
  const token = tokenStorage.get()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Expired/invalid session → notify the auth store (registered in authStore.ts)
let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler
}

apiClient.interceptors.response.use(
  (r) => r,
  (error) => {
    const isLogin = error.config?.url?.startsWith('/auth/login')
    if (error.response?.status === 401 && !isLogin) {
      onUnauthorized?.()
    }
    return Promise.reject(error)
  }
)

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export const authApi = {
  login: (email: string, password: string) =>
    apiClient
      .post<TokenResponse>('/auth/login', { email, password })
      .then((r) => r.data),

  register: (email: string, password: string, full_name?: string) =>
    apiClient
      .post<TokenResponse>('/auth/register', { email, password, full_name })
      .then((r) => r.data),

  me: () => apiClient.get<CurrentUser>('/auth/me').then((r) => r.data),
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

export const searchApi = {
  search: (req: SearchRequest) =>
    apiClient.post<SearchResponse>('/search', req).then((r) => r.data),

  searchGet: (params: SearchRequest) =>
    apiClient
      .get<SearchResponse>('/search', { params: { q: params.query, ...params } })
      .then((r) => r.data),

  getFilters: () =>
    apiClient.get<SearchFilters>('/search/filters').then((r) => r.data),
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

export const chatApi = {
  ask: (req: ChatRequest) =>
    apiClient.post<ChatResponse>('/chat', req).then((r) => r.data),

  rate: (message_id: string, helpful: boolean, comment?: string) =>
    apiClient.post('/chat/rate', { message_id, helpful, comment }),

  listSessions: (limit = 20, offset = 0) =>
    apiClient
      .get<{ sessions: { id: string; created_at: string; updated_at: string }[] }>(
        '/chat/sessions',
        { params: { limit, offset } }
      )
      .then((r) => r.data),
}

// ---------------------------------------------------------------------------
// Feed
// ---------------------------------------------------------------------------

export const feedApi = {
  getFeed: (params?: {
    limit?: number
    offset?: number
    entry_type?: string
    service_name?: string
    unread_only?: boolean
  }) => apiClient.get<FeedResponse>('/feed', { params }).then((r) => r.data),

  getUnread: () =>
    apiClient.get<{ unread: number }>('/feed/unread').then((r) => r.data),

  markRead: (entry_id: number) =>
    apiClient.post(`/feed/${entry_id}/read`),
}

// ---------------------------------------------------------------------------
// Reports (incident reports — Phase 5)
// ---------------------------------------------------------------------------

export interface GenerateReportPayload {
  incident_id: string
  title: string
  severity?: string
  started_at?: string
  resolved_at?: string
  context_logs?: string[]
  affected_services?: string[]
}

export async function generateReport(payload: GenerateReportPayload): Promise<IncidentReport> {
  const { data } = await apiClient.post<IncidentReport>('/reports/generate', payload)
  return data
}

export async function listReports(params?: {
  status?: string
  severity?: string
  page?: number
  page_size?: number
}): Promise<PaginatedResponse<IncidentReport>> {
  const { data } = await apiClient.get<PaginatedResponse<IncidentReport>>('/reports', { params })
  return data
}

export async function getReport(id: string): Promise<IncidentReport> {
  const { data } = await apiClient.get<IncidentReport>(`/reports/${id}`)
  return data
}

export async function updateReport(
  id: string,
  patch: Partial<IncidentReport>
): Promise<IncidentReport> {
  const { data } = await apiClient.patch<IncidentReport>(`/reports/${id}`, patch)
  return data
}

export async function deleteReport(id: string): Promise<void> {
  await apiClient.delete(`/reports/${id}`)
}

/** Download a rendered report (the gateway streams the file from the audit service). */
export async function exportReport(id: string, format: 'pdf' | 'markdown'): Promise<Blob> {
  const { data } = await apiClient.get<Blob>(`/reports/${id}/export/${format}`, {
    responseType: 'blob',
  })
  return data
}

// ---------------------------------------------------------------------------
// Outcomes (feedback loop)
// ---------------------------------------------------------------------------

export interface CreateOutcomePayload {
  incident_id: string
  report_id?: string
  alert_id?: string
  verdict: IncidentOutcome['verdict']
  rca_accurate?: boolean
  forecast_accurate?: boolean
  time_to_detect_seconds?: number
  time_to_resolve_seconds?: number
  action_taken?: string
  fired_indicators?: string[]
  forecast_score_at_incident?: number
  notes?: string
}

export async function createOutcome(payload: CreateOutcomePayload): Promise<IncidentOutcome> {
  const { data } = await apiClient.post<IncidentOutcome>('/outcomes', payload)
  return data
}

export async function listOutcomes(params?: {
  incident_id?: string
  verdict?: string
  page?: number
}): Promise<PaginatedResponse<IncidentOutcome>> {
  const { data } = await apiClient.get<PaginatedResponse<IncidentOutcome>>('/outcomes', { params })
  return data
}

// ---------------------------------------------------------------------------
// Deployments
// ---------------------------------------------------------------------------

export async function listDeployments(params?: {
  service_name?: string
  environment?: string
  page?: number
}): Promise<PaginatedResponse<DeploymentSnapshot>> {
  const { data } = await apiClient.get<PaginatedResponse<DeploymentSnapshot>>('/deployments', {
    params,
  })
  return data
}

export async function compareDeployments(
  baseId: string,
  headId: string
): Promise<DeploymentComparison> {
  const { data } = await apiClient.get<DeploymentComparison>('/deployments/compare', {
    params: { base_id: baseId, head_id: headId },
  })
  return data
}

// ---------------------------------------------------------------------------
// Forecasting weights
// ---------------------------------------------------------------------------

export async function listWeights(): Promise<{ items: ForecastWeight[] }> {
  const { data } = await apiClient.get<{ items: ForecastWeight[] }>('/feedback/weights')
  return data
}

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------

export async function listUsers(params?: { page?: number }): Promise<PaginatedResponse<User>> {
  const { data } = await apiClient.get<PaginatedResponse<User>>('/users', { params })
  return data
}

export async function updateUser(
  id: string,
  patch: { role?: User['role']; is_active?: boolean; full_name?: string }
): Promise<User> {
  const { data } = await apiClient.patch<User>(`/users/${id}`, patch)
  return data
}

// ---------------------------------------------------------------------------
// Analysis & correlation (Phase 3)
// ---------------------------------------------------------------------------

/** Fleet health summary — all active services. */
export async function getFleetHealth(): Promise<FleetHealth> {
  const { data } = await apiClient.get<FleetHealth>('/analysis/health')
  return data
}

/** Single service health state. */
export async function getServiceHealth(serviceId: string): Promise<ServiceHealthState> {
  const { data } = await apiClient.get<ServiceHealthState>(`/analysis/health/${serviceId}`)
  return data
}

/** Deduplicated errors for a service. */
export async function listDedupErrors(
  serviceId: string,
  params?: { limit?: number; severity?: string }
): Promise<DedupError[]> {
  const { data } = await apiClient.get<DedupError[]>(`/analysis/dedup/${serviceId}`, { params })
  return data
}

/** Error clusters for a service. */
export async function listClusters(
  serviceId: string,
  params?: { active_only?: boolean; limit?: number }
): Promise<ErrorCluster[]> {
  const { data } = await apiClient.get<ErrorCluster[]>(`/analysis/clusters/${serviceId}`, { params })
  return data
}

/** List anomaly events. */
export async function listAnomalies(params?: {
  service_id?: string
  resolved?: boolean
  limit?: number
}): Promise<AnomalyEvent[]> {
  const { data } = await apiClient.get<AnomalyEvent[]>('/analysis/anomalies', { params })
  return data
}

/** Resolve an anomaly. */
export async function resolveAnomaly(anomalyId: string, resolved_by: string): Promise<AnomalyEvent> {
  const { data } = await apiClient.post<AnomalyEvent>(`/analysis/anomalies/${anomalyId}/resolve`, {
    resolved_by,
  })
  return data
}

/** Run RCA for a service. */
export async function runRCA(serviceId: string, window_minutes = 30): Promise<RCAResult> {
  const { data } = await apiClient.post<RCAResult>(`/analysis/rca/${serviceId}`, { window_minutes })
  return data
}

/** List deployment regressions. */
export async function listRegressions(params?: {
  service_id?: string
  acknowledged?: boolean
  limit?: number
}): Promise<DeploymentRegression[]> {
  const { data } = await apiClient.get<DeploymentRegression[]>('/analysis/regressions', { params })
  return data
}

/** Acknowledge a regression. */
export async function acknowledgeRegression(
  regressionId: string,
  acknowledged_by: string
): Promise<DeploymentRegression> {
  const { data } = await apiClient.post<DeploymentRegression>(
    `/analysis/regressions/${regressionId}/acknowledge`,
    { acknowledged_by }
  )
  return data
}

/** Manual deployment comparison. */
export async function compareDeploymentVersions(params: {
  service_id: string
  baseline_version: string
  head_version: string
  baseline_deployed_at?: string
  head_deployed_at?: string
  window_hours?: number
}): Promise<DeploymentRegression[]> {
  const { data } = await apiClient.post<DeploymentRegression[]>('/analysis/compare', params)
  return data
}
