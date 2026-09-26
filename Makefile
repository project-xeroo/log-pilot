<<<<<<< HEAD
.PHONY: up down build logs ps \
        migrate seed \
        test test-api test-ai test-forecasting test-audit \
        lint frontend-install frontend-dev

# ── Docker Compose ────────────────────────────────────────────────────────
up:
	docker compose up -d
=======
.PHONY: help dev up down migrate test test-parsers test-redaction logs clean

# ── Help ───────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "LogPilot — Phase 1 Development Commands"
	@echo ""
	@echo "  make dev          Start all services (infra + app)"
	@echo "  make up           Same as dev"
	@echo "  make down         Stop and remove containers"
	@echo "  make migrate      Run database migrations"
	@echo "  make test         Run all tests"
	@echo "  make test-parsers Run parser unit tests only"
	@echo "  make test-redact  Run PII redaction unit tests only"
	@echo "  make logs         Tail all service logs"
	@echo "  make clean        Remove volumes and reset local state"
	@echo ""

# ── Local development ──────────────────────────────────────────────────────
dev: up

up:
	docker compose up --build -d
	@echo ""
	@echo "Services starting..."
	@echo "  API Gateway:         http://localhost:8000/docs"
	@echo "  Ingestion Service:   http://localhost:8001/docs"
	@echo "  MinIO Console:       http://localhost:9001  (admin/minioadmin)"
	@echo ""
>>>>>>> e364a7a0c05430efb740325dea92835d994c1bc0

down:
	docker compose down

<<<<<<< HEAD
build:
	docker compose build

logs:
	docker compose logs -f

ps:
	docker compose ps

# ── Database migrations ───────────────────────────────────────────────────
migrate:
	docker compose exec api-gateway alembic upgrade head
	docker compose exec forecasting-service alembic upgrade head

# Dev helper: create all tables directly (no Alembic, for local prototyping)
db-init:
	docker compose exec api-gateway python -c "from shared.utils import init_db; init_db(); print('DB initialised')"

# ── Testing ───────────────────────────────────────────────────────────────
test: test-api test-ai test-forecasting test-audit

test-api:
	docker compose exec api-gateway pytest tests/ -v

test-ai:
	docker compose exec ai-service pytest tests/ -v

test-forecasting:
	docker compose exec forecasting-service pytest tests/ -v

test-audit:
	docker compose exec audit-service pytest tests/ -v

# ── Frontend ──────────────────────────────────────────────────────────────
frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

# ── Linting ───────────────────────────────────────────────────────────────
lint:
	cd frontend && npm run lint

# ── RBAC smoke test ───────────────────────────────────────────────────────
rbac-smoke:
	@echo "Running RBAC smoke tests against http://localhost:8000 ..."
	python docs/scripts/rbac_smoke_test.py
=======
# ── Database migrations ─────────────────────────────────────────────────────
migrate:
	docker compose run --rm migrate

migrate-local:
	cd services/log-ingestion-service && alembic upgrade head

# ── Tests ──────────────────────────────────────────────────────────────────
test:
	pytest services/log-ingestion-service/tests/ \
	       services/processing-worker/tests/ \
	       -v --tb=short

test-parsers:
	pytest services/log-ingestion-service/tests/test_parsers.py -v

test-redact:
	pytest services/log-ingestion-service/tests/test_redaction.py -v

# ── Logs ───────────────────────────────────────────────────────────────────
logs:
	docker compose logs -f api-gateway log-ingestion-service processing-worker

logs-worker:
	docker compose logs -f processing-worker

# ── Cleanup ────────────────────────────────────────────────────────────────
clean:
	docker compose down -v --remove-orphans
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
>>>>>>> e364a7a0c05430efb740325dea92835d994c1bc0
