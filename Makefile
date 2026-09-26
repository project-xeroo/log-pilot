.PHONY: help dev up down build ps logs logs-worker migrate migrate-local create-admin \
        test test-gateway test-ai test-ingestion test-worker test-forecasting \
        test-parsers test-redact rbac-smoke \
        frontend-install frontend-dev frontend-build frontend-typecheck lint clean

# Every service has its own top-level `app` package, so each suite runs in its
# own pytest process (from the repo root, which puts `shared` on sys.path).
PYTEST := python -m pytest -p no:cacheprovider

# ── Help ───────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "LogPilot — Development Commands"
	@echo ""
	@echo "  make up             Build and start all services (infra + app + console)"
	@echo "  make down           Stop and remove containers"
	@echo "  make migrate        Run database migrations"
	@echo "  make create-admin   Create an admin user (EMAIL=... required)"
	@echo "  make test           Run every backend test suite"
	@echo "  make frontend-dev   Run the console with hot reload on :5173"
	@echo "  make logs           Tail application logs"
	@echo "  make clean          Remove volumes and reset local state"
	@echo ""

# ── Docker Compose ─────────────────────────────────────────────────────────
dev: up

up:
	docker compose up --build -d
	@echo ""
	@echo "Services starting..."
	@echo "  Console:             http://localhost:3000"
	@echo "  API Gateway:         http://localhost:8000/docs"
	@echo "  AI Service:          http://localhost:8002/docs"
	@echo "  Object store (S3):   http://localhost:8333"
	@echo ""

down:
	docker compose down

build:
	docker compose build

ps:
	docker compose ps

logs:
	docker compose logs -f api-gateway ai-service log-ingestion-service processing-worker forecasting-worker

logs-worker:
	docker compose logs -f processing-worker

# ── Database ───────────────────────────────────────────────────────────────
migrate:
	docker compose run --rm migrate

migrate-local:
	cd services/log-ingestion-service && alembic upgrade head

# First admin account (self-registration cannot create admin/sre/manager)
create-admin:
	@test -n "$(EMAIL)" || (echo "Usage: make create-admin EMAIL=you@example.com" && exit 1)
	docker compose exec api-gateway python -m app.cli create-user --email $(EMAIL) --role admin

# ── Tests ──────────────────────────────────────────────────────────────────
test: test-gateway test-ai test-ingestion test-worker test-forecasting

test-gateway:
	$(PYTEST) services/api-gateway/tests

test-ai:
	$(PYTEST) services/ai-service/tests

test-ingestion:
	$(PYTEST) services/log-ingestion-service/tests

test-worker:
	$(PYTEST) services/processing-worker/tests

test-forecasting:
	$(PYTEST) services/forecasting-service/tests

test-parsers:
	$(PYTEST) services/log-ingestion-service/tests/test_parsers.py -v

test-redact:
	$(PYTEST) services/log-ingestion-service/tests/test_redaction.py -v

rbac-smoke:
	@echo "Running RBAC smoke tests against http://localhost:8000 ..."
	python docs/scripts/rbac_smoke_test.py

# ── Frontend ───────────────────────────────────────────────────────────────
frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

frontend-typecheck:
	cd frontend && npm run typecheck

lint:
	cd frontend && npm run lint

# ── Cleanup ────────────────────────────────────────────────────────────────
clean:
	docker compose down -v --remove-orphans
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
