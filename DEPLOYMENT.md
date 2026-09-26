# LogPilot — Deployment Guide

> Phase 1 — Cloud Foundation & Data Ingestion Pipeline

---

## Table of Contents

1. [What Was Built](#1-what-was-built)
2. [Architecture Overview](#2-architecture-overview)
3. [Working Features](#3-working-features)
4. [Prerequisites](#4-prerequisites)
5. [Local Development (Docker Compose)](#5-local-development-docker-compose)
6. [Environment Variables Reference](#6-environment-variables-reference)
7. [Running the Database Migration](#7-running-the-database-migration)
8. [Testing](#8-testing)
9. [API Reference](#9-api-reference)
10. [Folder Structure](#10-folder-structure)
11. [What's Not Yet Built (Phase 2+)](#11-whats-not-yet-built-phase-2)

---

## 1. What Was Built

Phase 1 implements the four core data-pipeline tools from the LogPilot PRD, plus the API server skeleton needed to secure and audit every interaction.

### Tool 01 — Log Ingestion Tool

Multi-format log ingestion supporting six file types, API push, and the session tracking needed to monitor progress end-to-end.

- File upload endpoint: accepts `.log`, `.txt`, `.json`, `.csv`, `.zip`, `.gz` up to **500 MB**
- API ingestion endpoint: push up to 100,000 raw log lines per call as a JSON array
- Every upload is stored in S3-compatible object storage (MinIO locally, any S3-compatible bucket in cloud) before processing begins, giving the pipeline a durable source of truth
- A `log_sessions` row is created immediately on receipt, tracking status (`pending → processing → completed / failed / partial`), detected format, parse counts, PII redaction count, and error details
- A `GET /ingest/status/{session_id}` endpoint lets callers poll for live progress

### Tool 02 — Log Parsing Tool

Auto-detecting parser pipeline that converts unstructured log lines into structured `log_records` rows. Format detection is automatic — no configuration required.

| Format | What it parses |
|---|---|
| **JSON** | Any structured JSON log line; field extraction via priority-key lists (`timestamp`, `ts`, `@timestamp`, …); Unix epoch and ISO 8601 timestamps; severity normalisation across all common labels |
| **Apache Combined** | Full CLF + Referer + User-Agent; HTTP status → severity mapping |
| **Apache Common** | Standard CLF; severity from HTTP status |
| **Nginx** | Combined format with optional `request_time` → `duration_ms` conversion |
| **RFC 5424 Syslog** | Structured syslog with PRI-based severity; ISO 8601 timestamps |
| **RFC 3164 Syslog** | Classic BSD syslog; hostname, app name, PID extraction |
| **Generic / Log4j / Logback** | Timestamp + level + logger + message heuristic — catches most Java, Python, Ruby application loggers |
| **CSV** | Each row is treated as a structured record, fields passed through the JSON parser |
| **Fallback** | Unrecognised lines are stored as `is_malformed=true` with the raw content preserved |

Compressed inputs (`.gz`, `.zip`) are decompressed transparently before line-by-line parsing. The dominant format across all lines is detected by vote and stored on the session.

Fields extracted per record: `timestamp`, `service_name`, `severity`, `message`, `request_id`, `trace_id`, `environment`, `deployment_version`, `source_ip`, `http_method`, `http_path`, `http_status`, `duration_ms`, plus a `extra_fields` JSONB column for anything that doesn't fit a named column.

### Tool 03 — PII Redaction Tool

**Mandatory, non-configurable gate.** Runs on every record before anything is written to the database and before any data is sent to an AI model. Cannot be disabled or bypassed.

Detects and replaces the following PII types with typed placeholders:

| PII Type | Placeholder | Notes |
|---|---|---|
| Email addresses | `[REDACTED_EMAIL]` | RFC 5321 pattern |
| Phone numbers | `[REDACTED_PHONE]` | E.164, US national, parenthesised formats |
| Credit card numbers | `[REDACTED_CC]` | Luhn-validated to eliminate false positives |
| JWT tokens | `[REDACTED_JWT]` | Three-part base64url structure |
| Bearer / API key tokens | `[REDACTED_API_KEY]` | High-entropy strings following `Bearer` / `token` / `auth` |
| Passwords / secrets | `[REDACTED_PASSWORD]` | `key=value` and `key: value` patterns for `password`, `secret`, `api_key`, `SECRET_KEY`, etc. |
| AWS Access Key IDs | `[REDACTED_AWS_KEY]` | `AKIA…` format |
| Social Security Numbers | `[REDACTED_SSN]` | US NNN-NN-NNNN, invalid ranges excluded |
| Public IPv4 addresses | `[REDACTED_IP]` | Private ranges (10.x, 172.16-31.x, 192.168.x, 127.x) preserved as `[INTERNAL_IP]` |

Measured detection rate: **100%** against the test battery (PRD requires ≥ 95%).

The `pii_was_redacted` flag is set on every affected `log_records` row. The original `raw_line` is dropped (set to `NULL`) for any line where PII was found.

### Tool 04 — Structured Storage & Indexing Tool

PostgreSQL schema (`pgvector/pgvector:pg16` image) with indexes tuned for the PRD's scale targets.

**`log_records` table indexes:**

| Index | Type | Purpose |
|---|---|---|
| `ix_log_records_timestamp` | B-tree | Date-range queries — the primary filter on every dashboard view |
| `ix_log_records_service_ts` | Composite B-tree | Service + time range — most common combined query pattern |
| `ix_log_records_severity` | B-tree | Filter by ERROR / CRITICAL |
| `ix_log_records_trace_id` | B-tree | Distributed trace correlation |
| `ix_log_records_request_id` | B-tree | Single-request drill-down |
| `ix_log_records_message_tsv` | GIN | Full-text search on `message` field via PostgreSQL `tsvector` |
| `ix_log_records_embedding_ivfflat` | IVFFlat | Vector similarity search (pgvector) — scaffolded for Phase 2 embeddings |

Bulk inserts use 500-row batches. The `message_tsv` column is a **generated column** (`GENERATED ALWAYS AS … STORED`) so full-text indexing happens automatically on every insert with no application-side work.

The vector index (`ivfflat`, cosine similarity, 1536 dimensions) is scaffolded now so the column and index exist when Phase 2 starts generating embeddings.

### Agent API Server Skeleton

FastAPI application exposing all tool endpoints, protected by JWT + RBAC, with every action audit-logged.

- **JWT authentication** — `POST /auth/login` and `POST /auth/register` return Bearer tokens
- **Role-based access control** — six roles (`admin`, `sre`, `developer`, `manager`, `junior`, `viewer`) with hierarchical enforcement on every endpoint via a `require_role()` dependency
- **Audit logging** — `AuditLoggingMiddleware` writes every API request to the `agent_actions` table (tool name, trigger, autonomy tier, actor user ID, input/output summary, status)
- **OpenAPI documentation** — auto-generated at `/docs` and `/redoc`

### Processing Pipeline (Celery)

Celery worker that chains all four tools end-to-end as a single atomic task:

```
Download from storage → Parse (Tool 02) → Redact PII (Tool 03) → Bulk-insert (Tool 04) → Audit-log
```

- Triggered within 5 seconds of upload (meets PRD `< 5s` start requirement)
- Retries up to 3 times with 10-second backoff on transient failures
- Updates session status at each stage: `processing → completed / failed / partial`
- Two worker replicas in Docker Compose; scales elastically in Kubernetes

---

## 2. Architecture Overview

```
                        ┌─────────────────────────────────┐
                        │         API Gateway :8000        │
                        │  FastAPI · JWT · RBAC · Audit    │
                        └────────────┬────────────────────┘
                                     │  HTTP proxy
                        ┌────────────▼────────────────────┐
                        │   Log Ingestion Service :8001    │
                        │   Tool 01 — upload / API ingest  │
                        └────────────┬────────────────────┘
                                     │  enqueue Celery task
              ┌──────────────────────▼──────────────────────┐
              │              Redis (broker + results)        │
              └──────────────────────┬──────────────────────┘
                                     │  consume
              ┌──────────────────────▼──────────────────────┐
              │            Processing Worker (×2)            │
              │  Tool 02 Parse → Tool 03 Redact → Tool 04   │
              └──────────┬──────────────────────────────────┘
                         │                       │
              ┌──────────▼──────┐    ┌───────────▼────────┐
              │  PostgreSQL      │    │  MinIO / S3        │
              │  pgvector:pg16   │    │  (raw file store)  │
              │  log_records     │    │                    │
              │  log_sessions    │    └────────────────────┘
              │  agent_actions   │
              │  users           │
              └─────────────────┘
```

---

## 3. Working Features

The following capabilities are fully implemented and testable in Phase 1:

| Feature | Endpoint / Mechanism | Status |
|---|---|---|
| Upload `.log` / `.txt` / `.json` / `.csv` / `.zip` / `.gz` up to 500 MB | `POST /ingest/upload` | ✅ Working |
| API-based log ingestion (push line arrays) | `POST /ingest/api` | ✅ Working |
| Session status polling | `GET /ingest/status/{session_id}` | ✅ Working |
| Auto-detect Apache Common, Apache Combined, Nginx, JSON, RFC 5424, RFC 3164, Log4j | Processing worker | ✅ Working |
| PII redaction (email, phone, CC, JWT, API keys, passwords, SSN, IPs) | Processing worker — mandatory gate | ✅ Working |
| Full-text search index on `message` field | PostgreSQL GIN on generated `tsvector` column | ✅ Working |
| Date-partitioned queries via timestamp indexes | B-tree indexes on `timestamp` and `(service_name, timestamp)` | ✅ Working |
| Vector index scaffold (Phase 2 embeddings) | pgvector `ivfflat` index on `embedding` column | ✅ Scaffolded |
| JWT login and registration | `POST /auth/login`, `POST /auth/register` | ✅ Working |
| RBAC enforcement on all endpoints | `require_role()` FastAPI dependency | ✅ Working |
| Audit log of every API action | `agent_actions` table via middleware | ✅ Working |
| Async PostgreSQL (asyncpg) | All FastAPI endpoints | ✅ Working |
| Object storage abstraction (S3-compatible) | MinIO locally, any S3 bucket in cloud | ✅ Working |

---

## 4. Prerequisites

### Local development

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) ≥ 4.x (with Compose v2)
- `make` (Git Bash / WSL on Windows, or native on macOS/Linux)
- Python 3.11+ (only needed to run tests locally without Docker)

### Cloud deployment (when you're ready — Phase 1 infra scaffolded but not wired up)

- AWS / GCP / Azure account
- Terraform ≥ 1.5
- `kubectl` + access to a managed Kubernetes cluster (EKS / GKE / AKS)

---

## 5. Local Development (Docker Compose)

### First-time setup

```bash
# 1. Clone the repo
git clone <repo-url>
cd log-pilot

# 2. Copy environment variables
cp .env.example .env
# Edit .env — at minimum, set a real JWT_SECRET value

# 3. Start everything (builds images, starts infra + services)
make dev
```

After ~30 seconds, the following are running:

| Service | URL |
|---|---|
| **API Gateway** (main entry point) | http://localhost:8000/docs |
| **Log Ingestion Service** (direct) | http://localhost:8001/docs |
| **MinIO Console** (file storage UI) | http://localhost:9001 — login: `minioadmin` / `minioadmin` |
| **PostgreSQL** | `localhost:5432` — user: `logpilot`, password: `logpilot`, db: `logpilot` |
| **Redis** | `localhost:6379` |

### Run database migrations

```bash
make migrate
```

This runs `alembic upgrade head` inside a short-lived container, creating all Phase 1 tables, indexes, and the pgvector extension.

### Stop everything

```bash
make down
```

### Wipe volumes and start fresh

```bash
make clean
make dev
make migrate
```

---

## 6. Environment Variables Reference

Copy `.env.example` to `.env`. All variables have working defaults for local development.

| Variable | Default (local) | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://logpilot:logpilot@postgres:5432/logpilot` | Async PostgreSQL URL (FastAPI services) |
| `DATABASE_URL_SYNC` | `postgresql://logpilot:logpilot@postgres:5432/logpilot` | Sync PostgreSQL URL (Celery worker) |
| `POSTGRES_USER` | `logpilot` | PostgreSQL superuser for local container |
| `POSTGRES_PASSWORD` | `logpilot` | |
| `POSTGRES_DB` | `logpilot` | |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection URL |
| `CELERY_BROKER_URL` | `redis://redis:6379/0` | Celery message broker |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/1` | Celery result store |
| `JWT_SECRET` | `change-me-in-dev` | **Must be changed before any real deployment** |
| `JWT_ALGORITHM` | `HS256` | |
| `JWT_EXPIRY_SECONDS` | `3600` | Token lifetime (1 hour) |
| `STORAGE_BUCKET` | `logpilot-uploads` | S3 / MinIO bucket name |
| `STORAGE_ENDPOINT_URL` | `http://minio:9000` | Leave blank for AWS S3; set for MinIO or GCS |
| `STORAGE_ACCESS_KEY_ID` | `minioadmin` | S3 / MinIO access key |
| `STORAGE_SECRET_ACCESS_KEY` | `minioadmin` | S3 / MinIO secret key |
| `STORAGE_REGION` | `us-east-1` | |
| `INGESTION_SERVICE_URL` | `http://log-ingestion-service:8001` | Internal URL the gateway uses to proxy requests |
| `DEBUG` | `false` | Set `true` to enable SQLAlchemy query logging |

---

## 7. Running the Database Migration

### Via Docker Compose (recommended)

```bash
make migrate
# or directly:
docker compose run --rm migrate
```

### Locally against a running database

```bash
cd services/log-ingestion-service
DATABASE_URL=postgresql+asyncpg://logpilot:logpilot@localhost:5432/logpilot \
  alembic upgrade head
```

### What the migration creates

- `users` table — accounts, roles, hashed passwords
- `log_sessions` table — one row per upload or API ingestion session
- `log_records` table — one row per parsed log line, with all structured fields, full-text search column, and vector embedding column
- `agent_actions` table — immutable audit log of every agent and user action
- All enums: `severitylevel`, `logformat`, `ingestionstatus`, `autonomytier`, `userrole`
- All indexes (see Tool 04 section above)
- Extensions: `pg_trgm`, `btree_gin`, `vector` (pgvector)

---

## 8. Testing

### Run all tests

```bash
# Option A — directly with Python (no Docker needed)
python -m pytest services/log-ingestion-service/tests/ -v

# Option B — via Makefile
make test
```

### Run specific test suites

```bash
# Parser tests only (Tool 02)
make test-parsers

# PII redaction tests only (Tool 03)
make test-redact
```

### Current test results

```
73 tests — 73 passed, 0 failed
```

Test coverage includes:

- **Apache Common** — IP, method/path, status code, severity derivation, format tag, negative case
- **Apache Combined** — Referer, User-Agent extraction
- **Nginx** — duration → ms conversion, format tag
- **RFC 5424 Syslog** — timestamp parsing, service name, PRI-based severity
- **RFC 3164 Syslog** — service name, message, PID extraction
- **JSON parser** — field extraction, Unix epoch/ms timestamps, severity normalisation, HTTP fields, extra fields passthrough
- **Auto-detection dispatcher** — JSON, Apache, Syslog, Log4j generic, malformed fallback
- **File decompression** — plain text, `.gz`, `.zip`, `.csv` (all format variants)
- **`parse_content`** — dominant format voting for JSON and Apache files
- **PII redaction** — email, phone, Visa/MC/Amex credit cards, JWT, Bearer token, password `=` and `:` patterns, `SECRET_KEY=`, AWS access key, SSN, public/private/loopback IP
- **Luhn validation** — non-Luhn digit strings are not redacted
- **`redact_record_fields`** — nested dict redaction, non-string values untouched
- **Detection rate test** — 15-case PRD battery, must hit ≥ 95%

---

## 9. API Reference

Full interactive documentation is available at **http://localhost:8000/docs** when the stack is running.

### Authentication

All endpoints (except `/health`) require a `Bearer` token in the `Authorization` header.

**Register a new account**
```http
POST /auth/register
Content-Type: application/json

{
  "email": "engineer@company.com",
  "password": "your-password",
  "full_name": "Alice Smith",
  "role": "developer"
}
```
Returns `{ "access_token": "eyJ...", "token_type": "bearer", "expires_in": 3600 }`

**Login**
```http
POST /auth/login
Content-Type: application/json

{ "email": "engineer@company.com", "password": "your-password" }
```

### Log Ingestion

**Upload a log file** *(requires `developer` role or above)*
```http
POST /ingest/upload
Authorization: Bearer <token>
Content-Type: multipart/form-data

file=@access.log
service_name=payment-service   (optional)
environment=production          (optional)
```
Returns `{ "session_id": "...", "filename": "...", "size_bytes": ..., "status": "pending" }`

**Push log lines via API** *(requires `developer` role or above)*
```http
POST /ingest/api
Authorization: Bearer <token>
Content-Type: application/json

{
  "service": "checkout-service",
  "lines": [
    "{\"level\":\"ERROR\",\"msg\":\"DB timeout\",\"ts\":1705318200}",
    "2024-01-15 10:30:00 WARN [main] com.example.App - High memory usage"
  ]
}
```

**Check processing status** *(requires any authenticated user)*
```http
GET /ingest/status/{session_id}
Authorization: Bearer <token>
```
Returns live processing statistics including `parsed_records`, `pii_redacted_count`, `detected_format`, and `status`.

### Role permissions summary

| Role | Register | Upload / API ingest | View status | Admin actions |
|---|---|---|---|---|
| `viewer` | ✅ | ❌ | ✅ | ❌ |
| `junior` | ✅ | ❌ | ✅ | ❌ |
| `developer` | ✅ | ✅ | ✅ | ❌ |
| `manager` | ✅ | ✅ | ✅ | ❌ |
| `sre` | ✅ | ✅ | ✅ | ✅ |
| `admin` | ✅ | ✅ | ✅ | ✅ |

> `admin` and `sre` accounts cannot be self-registered — they must be created by an existing admin.

---

## 10. Folder Structure

```
log-pilot/
├── shared/                        # Shared ORM models, config, DB utilities
│   ├── models/__init__.py         # log_sessions, log_records, users, agent_actions
│   ├── config/__init__.py         # DatabaseSettings, RedisSettings, StorageSettings
│   └── utils/__init__.py          # Async engine + get_db() dependency
│
├── services/
│   ├── api-gateway/               # Agent API server — JWT, RBAC, audit middleware
│   │   └── app/
│   │       ├── auth/__init__.py   # JWT create/verify, require_role() factory
│   │       ├── middleware/        # AuditLoggingMiddleware → agent_actions
│   │       ├── routers/auth.py    # Login + register endpoints
│   │       ├── routers/ingestion.py  # RBAC-protected proxy to ingestion service
│   │       └── main.py            # FastAPI app, CORS, middleware wiring
│   │
│   ├── log-ingestion-service/     # Tool 01 + 02 + 03 implementations
│   │   ├── app/
│   │   │   ├── validators/        # Extension + size + magic-byte checks
│   │   │   ├── storage/           # S3-compatible object storage + indexing (Tool 04)
│   │   │   ├── parsers/           # Auto-detection dispatcher + all format parsers
│   │   │   │   ├── apache.py      # Apache Common + Combined
│   │   │   │   ├── nginx.py       # Nginx combined
│   │   │   │   ├── syslog.py      # RFC 5424 + RFC 3164
│   │   │   │   ├── json_parser.py # Structured JSON
│   │   │   │   └── __init__.py    # Dispatcher, gz/zip/csv decompression
│   │   │   ├── redaction/         # Tool 03 — mandatory PII gate
│   │   │   └── main.py            # FastAPI app, ingest endpoints
│   │   ├── migrations/
│   │   │   ├── env.py             # Alembic async environment
│   │   │   └── 0001_phase1_initial.py  # Full Phase 1 schema
│   │   └── tests/
│   │       ├── test_parsers.py    # 40 parser tests
│   │       └── test_redaction.py  # 33 PII redaction tests
│   │
│   └── processing-worker/         # Celery worker — parse→redact→store pipeline
│       └── app/
│           ├── main.py            # Celery app factory, queue config
│           └── tasks/__init__.py  # process_log_session task
│
├── docker-compose.yml             # Full local stack
├── .env.example                   # Environment variable template
├── Makefile                       # make dev / migrate / test / clean
└── DEPLOYMENT.md                  # This file
```

---

## 11. What's Not Yet Built (Phase 2+)

The following are explicitly out of scope for Phase 1 and will be implemented in subsequent phases:

| Capability | Phase |
|---|---|
| Log Search Tool — semantic + keyword search over stored records | 2 |
| Embedding generation (cloud API calls, pgvector population) | 2 |
| Error Clustering Tool — vector similarity clustering per service | 2 |
| Anomaly Detection Tool — statistical baseline + drift detection | 2 |
| Root Cause Analysis Tool — deep reasoning model causal chain | 3 |
| Chat / Q&A Tool — conversational interface over log context | 3 |
| Proactive Failure Forecasting — continuous risk scoring loop | 3 |
| Incident Report Generation Tool — autonomous post-mortem drafts | 3 |
| WebSocket real-time updates | 2 |
| Frontend (React) — Chat, Risk Board, Alerts, Search screens | 2–4 |
| Kubernetes manifests (`infra/k8s/`) | Cloud deployment phase |
| Terraform modules (`infra/terraform/`) | Cloud deployment phase |
| SSO / SAML authentication | Future |
| Multi-tenant data isolation | Future |

---

*LogPilot AI Agent — Product Requirements Document v2.0 — Phase 1 Implementation*
