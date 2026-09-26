# LogPilot Phase 5 — API Reference

All endpoints are served by the **API Gateway** at `http://localhost:8000`.

## Authentication

All endpoints (except `/auth/token` and `/auth/register`) require a Bearer JWT:

```
Authorization: Bearer <token>
```

Obtain a token via `POST /auth/token` (form body: `username`, `password`).

---

## Auth

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/token` | Login — returns JWT |
| POST | `/auth/register` | Register new user |
| GET  | `/auth/me` | Current user info |

---

## Reports

| Method | Path | Min Role | Description |
|--------|------|----------|-------------|
| POST | `/reports/generate` | SRE | Ask AI service to draft a full incident report |
| GET  | `/reports` | Viewer | List reports (paginated) |
| GET  | `/reports/{id}` | Viewer | Get a single report |
| PATCH | `/reports/{id}` | SRE | Edit report sections |
| DELETE | `/reports/{id}` | Admin | Delete a report |
| GET | `/reports/{id}/export/pdf` | Developer | Download as PDF |
| GET | `/reports/{id}/export/markdown` | Developer | Download as Markdown |

### Generate request body

```json
{
  "incident_id": "INC-1234",
  "title": "Payment service latency spike",
  "severity": "high",
  "started_at": "2024-06-01T14:32:00Z",
  "resolved_at": "2024-06-01T16:05:00Z",
  "affected_services": ["payment-service", "api-gateway"],
  "context_logs": ["2024-06-01T14:32:00Z ERROR ..."]
}
```

---

## Outcomes (Feedback Loop)

| Method | Path | Min Role | Description |
|--------|------|----------|-------------|
| POST | `/outcomes` | SRE | Log an incident outcome; triggers weight update |
| GET  | `/outcomes` | Viewer | List outcomes |
| GET  | `/outcomes/{id}` | Viewer | Get a single outcome |

### Outcome request body

```json
{
  "incident_id": "INC-1234",
  "report_id": "uuid",
  "verdict": "true_positive",
  "rca_accurate": true,
  "forecast_accurate": true,
  "time_to_detect_seconds": 120,
  "time_to_resolve_seconds": 5580,
  "action_taken": "Rolled back deployment v2.3.1",
  "fired_indicators": ["error_rate_spike", "latency_p99_high"],
  "forecast_score_at_incident": 0.87
}
```

---

## Deployments

| Method | Path | Min Role | Description |
|--------|------|----------|-------------|
| POST | `/deployments` | SRE | Record a deployment snapshot |
| GET  | `/deployments` | Viewer | List deployments |
| GET  | `/deployments/{id}` | Viewer | Get a snapshot |
| GET  | `/deployments/compare?base_id=X&head_id=Y` | Developer | Config diff |

---

## Users (Admin only)

| Method | Path | Min Role | Description |
|--------|------|----------|-------------|
| GET  | `/users` | Admin | List all users |
| GET  | `/users/{id}` | Admin | Get a user |
| PATCH | `/users/{id}` | Admin | Update role / active status |
| DELETE | `/users/{id}` | Admin | Delete a user |

---

## Forecasting Weights (served by Forecasting Service on :8002)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/feedback/ingest` | Ingest an outcome verdict → update weights |
| GET  | `/feedback/weights` | List all indicator weights |
| GET  | `/feedback/weights/{indicator}` | Get one indicator |

---

## RBAC Matrix

| Permission | Admin | SRE | Developer | Viewer |
|------------|-------|-----|-----------|--------|
| report:create | ✓ | ✓ | — | — |
| report:read | ✓ | ✓ | ✓ | ✓ |
| report:update | ✓ | ✓ | — | — |
| report:export | ✓ | ✓ | ✓ | — |
| report:delete | ✓ | — | — | — |
| outcome:write | ✓ | ✓ | — | — |
| outcome:read | ✓ | ✓ | ✓ | ✓ |
| deployment:read | ✓ | ✓ | ✓ | ✓ |
| deployment:compare | ✓ | ✓ | ✓ | — |
| user:manage | ✓ | — | — | — |
| forecast:read | ✓ | ✓ | ✓ | ✓ |
