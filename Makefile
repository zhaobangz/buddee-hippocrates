# Buddi — local developer ergonomics.
#
# One-line local flow:
#   make install   # backend venv + pip deps, frontend npm install
#   make db        # docker Postgres+pgvector on :5433, CREATE EXTENSION vector
#   make migrate   # alembic upgrade head
#   make dev       # backend :8001 + frontend :5173 (python start_dev.py)
#   make test      # pytest -q + frontend Vitest
#   make lint      # ruff (backend) + eslint (frontend)
#
# Local Postgres uses postgres:postgres on port 5433 to match
# tests/conftest.py, so `make test` and a bare `pytest` hit the same DB.
# `migrate`/`dev` set BUDDI_TEST_MODE=1 only to satisfy the SEC-04
# `postgres:postgres` guard locally — never set it in production.
# Targets are idempotent and macOS-friendly. Override any var on the CLI,
# e.g. `make db DB_PORT=5544` or `make install PYTHON=python3.12`.

# ---- Tunables --------------------------------------------------------------
PYTHON      ?= python3
VENV        ?= venv
VENV_PY     := $(VENV)/bin/python

PG_CONTAINER ?= buddi-postgres
PG_IMAGE     ?= pgvector/pgvector:pg16
DB_USER      ?= postgres
DB_PASS      ?= postgres
DB_NAME      ?= buddi
DB_PORT      ?= 5433
DATABASE_URL ?= postgresql://$(DB_USER):$(DB_PASS)@localhost:$(DB_PORT)/$(DB_NAME)

# BUDDI_TEST_MODE=1 lets core.database accept the postgres:postgres dev
# credential locally (SEC-04). Production must use a real credential.
LOCAL_DB_ENV := DATABASE_URL=$(DATABASE_URL) BUDDI_TEST_MODE=1
RUFF_PATHS   := backend/ core/ tools/ scripts/ evals/ tests/

.DEFAULT_GOAL := help
.PHONY: help install venv db db-stop db-clean migrate dev test test-backend test-frontend lint lint-backend lint-frontend smoke clean

help: ## Show this help
	@echo "Buddi make targets:"
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# ---- Setup -----------------------------------------------------------------
venv: ## Create the Python virtualenv if missing
	@if [ ! -x "$(VENV_PY)" ]; then \
		echo ">> creating venv ($(PYTHON))"; \
		$(PYTHON) -m venv $(VENV); \
	else \
		echo ">> venv already present"; \
	fi

install: venv ## Install backend (pip) + frontend (npm install) dependencies
	$(VENV_PY) -m pip install --upgrade pip
	$(VENV_PY) -m pip install -r requirements.txt -r requirements-dev.txt
	@if [ -d frontend ]; then \
		echo ">> installing frontend deps (npm install)"; \
		cd frontend && npm install; \
	else \
		echo ">> no frontend/ — skipping frontend deps"; \
	fi

# ---- Database --------------------------------------------------------------
db: ## Start Postgres+pgvector (idempotent) and ensure the vector extension
	@command -v docker >/dev/null 2>&1 || { echo "docker not found — install Docker Desktop"; exit 1; }
	@docker info >/dev/null 2>&1 || { echo "docker daemon not running — start Docker Desktop"; exit 1; }
	@if docker ps -a --format '{{.Names}}' | grep -qx '$(PG_CONTAINER)'; then \
		echo ">> starting existing container $(PG_CONTAINER)"; \
		docker start $(PG_CONTAINER) >/dev/null; \
	else \
		echo ">> running new $(PG_IMAGE) as $(PG_CONTAINER) on :$(DB_PORT)"; \
		docker run -d --name $(PG_CONTAINER) \
			-e POSTGRES_USER=$(DB_USER) -e POSTGRES_PASSWORD=$(DB_PASS) -e POSTGRES_DB=$(DB_NAME) \
			-p $(DB_PORT):5432 $(PG_IMAGE) >/dev/null; \
	fi
	@echo ">> waiting for Postgres to accept connections"
	@for i in $$(seq 1 30); do \
		docker exec $(PG_CONTAINER) pg_isready -U $(DB_USER) >/dev/null 2>&1 && break; \
		sleep 1; \
		if [ $$i -eq 30 ]; then echo "Postgres did not become ready"; exit 1; fi; \
	done
	@docker exec $(PG_CONTAINER) psql -U $(DB_USER) -d $(DB_NAME) -c "CREATE EXTENSION IF NOT EXISTS vector" >/dev/null
	@echo ">> Postgres ready at $(DATABASE_URL)"

db-stop: ## Stop the local Postgres container
	@docker stop $(PG_CONTAINER) >/dev/null 2>&1 && echo ">> stopped $(PG_CONTAINER)" || echo ">> $(PG_CONTAINER) not running"

db-clean: ## Remove the local Postgres container (DESTROYS local data)
	@docker rm -f $(PG_CONTAINER) >/dev/null 2>&1 && echo ">> removed $(PG_CONTAINER)" || echo ">> nothing to remove"

migrate: ## Apply Alembic migrations (upgrade head)
	$(LOCAL_DB_ENV) $(VENV_PY) -m alembic upgrade head

smoke: ## Migration smoke test on a throwaway DB (upgrade head + round-trip)
	MIGRATION_SMOKE_DATABASE_URL=postgresql://$(DB_USER):$(DB_PASS)@localhost:$(DB_PORT)/postgres \
		$(VENV_PY) scripts/migrate_smoke.py --roundtrip

# ---- Run -------------------------------------------------------------------
dev: ## Run backend (:8001, --reload) + frontend (:5173) together
	$(LOCAL_DB_ENV) $(VENV_PY) start_dev.py

# ---- Test / Lint -----------------------------------------------------------
test: test-backend test-frontend ## Run backend pytest + frontend Vitest

test-backend: ## Run the Python test suite
	$(LOCAL_DB_ENV) $(VENV_PY) -m pytest -q

test-frontend: ## Run the frontend Vitest suite (passes with no tests yet)
	@if [ -d frontend/node_modules ]; then \
		cd frontend && npm test -- --passWithNoTests; \
	else \
		echo ">> frontend/node_modules missing — run 'make install' first"; \
	fi

lint: lint-backend lint-frontend ## Lint backend (ruff) + frontend (eslint)

lint-backend: ## Ruff lint of the Python tree (matches CI)
	$(VENV_PY) -m ruff check $(RUFF_PATHS)

lint-frontend: ## ESLint the frontend
	@if [ -d frontend/node_modules ]; then \
		cd frontend && npm run lint; \
	else \
		echo ">> frontend/node_modules missing — run 'make install' first"; \
	fi

clean: ## Remove caches (keeps venv and DB container)
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache
