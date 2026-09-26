# LogPilot Phase 5 — Architecture

## Service Map

```
┌──────────────┐     HTTPS/JWT     ┌──────────────────┐
│   Browser    │◄─────────────────►│   API Gateway    │  :8000
│  (React SPA) │                   │  FastAPI + RBAC  │
└──────────────┘                   └────────┬─────────┘
                                            │ HTTP (internal)
              ┌─────────────────────────────┼──────────────────────────┐
              │                             │                          │
   ┌──────────▼──────┐          ┌──────────▼──────┐        ┌──────────▼──────┐
   │   AI Service    │          │  Forecasting    │        │  Audit Service  │
   │  OpenAI / stub  │          │    Service      │        │  PDF/Markdown   │
   │    :8001        │          │   :8002         │        │   :8003         │
   └─────────────────┘          └────────┬────────┘        └─────────────────┘
                                         │
                                ┌────────▼────────┐
                                │   PostgreSQL    │
                                │  (all models)   │
                                └─────────────────┘
```

## Key Data Flows

### Report Generation (< 2 min SLA)

1. User clicks **Generate Report** → `POST /reports/generate`
2. API Gateway calls `POST http://ai-service:8001/reports/generate` with incident context
3. AI Service calls OpenAI (or returns stub), returns structured JSON
4. API Gateway persists `IncidentReport` row, returns draft
5. User edits in-app (PATCH /reports/{id}), then exports via Audit Service

### Feedback Loop

1. After resolution, user opens report → **Log Outcome**
2. `POST /outcomes` persists `IncidentOutcome`, then calls `POST http://forecasting-service:8002/feedback/ingest`
3. Forecasting Service updates `ForecastWeight` rows using online learning:
   - `true_positive` → weight += lr
   - `false_positive` → weight -= lr
   - `false_negative` → weight -= 0.5 × lr
4. Updated weights visible immediately in **Forecast Weights** screen

### Deployment Comparison

1. CI/CD pipeline `POST /deployments` on each deploy
2. User selects Base + Head in the Deployments screen
3. `GET /deployments/compare?base_id=X&head_id=Y` returns structured diff
4. UI renders per-key changes with colour-coded old/new values

## Database Tables (Phase 5)

| Table | Purpose |
|-------|---------|
| `users` | Auth + RBAC |
| `incident_reports` | Agent-drafted structured reports |
| `incident_outcomes` | Post-resolution feedback logging |
| `forecast_weights` | Persisted indicator weights, precision/recall |
| `deployment_snapshots` | Versioned config snapshots for comparison |
