.PHONY: up down build logs ps \
        migrate seed \
        test test-api test-ai test-forecasting test-audit \
        lint frontend-install frontend-dev

# ── Docker Compose ────────────────────────────────────────────────────────
up:
	docker compose up -d

down:
	docker compose down

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
