.PHONY: help env db-up backend-up up down logs migrate backend-install backend-lint backend-format backend-test frontend-install frontend-dev frontend-lint frontend-format prod-up prod-down prod-logs prod-bootstrap-admin

PY ?= python3
NPM ?= npm
DC ?= docker compose

help:
	@echo "Targets:"
	@echo "  env             Create .env from .env.example if missing"
	@echo "  up              Start db + backend (Docker Compose)"
	@echo "  db-up           Start only MariaDB"
	@echo "  backend-up      Start only backend (depends on db)"
	@echo "  migrate         Run Alembic migrations inside backend container"
	@echo "  down            Stop containers"
	@echo "  logs            Tail compose logs"
	@echo "  backend-install Install backend dev deps (local venv)"
	@echo "  backend-lint    Ruff lint backend"
	@echo "  backend-format  Ruff format backend"
	@echo "  backend-test    Run backend pytest"
	@echo "  frontend-install Install frontend deps"
	@echo "  frontend-dev     Run Vite dev server"
	@echo "  frontend-lint    ESLint frontend"
	@echo "  frontend-format  Prettier format frontend"
	@echo "  prod-up          Start production stack (db+backend+frontend+caddy)"
	@echo "  prod-down        Stop production stack"
	@echo "  prod-logs        Tail production stack logs"
	@echo "  prod-bootstrap-admin Bootstrap admin in production backend"

env:
	@test -f .env || cp .env.example .env

db-up: env
	@$(DC) up -d db

backend-up: env
	@$(DC) up -d --build backend

up: env
	@$(DC) up -d --build db backend

down:
	@$(DC) down

logs:
	@$(DC) logs -f

migrate:
	@$(DC) exec backend alembic upgrade head

backend-install:
	@cd backend && $(PY) -m pip install -r requirements-dev.txt

backend-lint:
	@cd backend && ruff check .

backend-format:
	@cd backend && ruff format .

backend-test:
	@cd backend && $(PY) -m pytest

frontend-install:
	@cd frontend && $(NPM) install

frontend-dev:
	@cd frontend && $(NPM) run dev

frontend-lint:
	@cd frontend && $(NPM) run lint

frontend-format:
	@cd frontend && $(NPM) run format

prod-up: env
	@$(DC) -f docker-compose.prod.yml up -d --build

prod-down:
	@$(DC) -f docker-compose.prod.yml down

prod-logs:
	@$(DC) -f docker-compose.prod.yml logs -f

prod-bootstrap-admin:
	@$(DC) -f docker-compose.prod.yml exec \
		-e BOOTSTRAP_ADMIN_EMAIL=$${BOOTSTRAP_ADMIN_EMAIL} \
		-e BOOTSTRAP_ADMIN_PASSWORD=$${BOOTSTRAP_ADMIN_PASSWORD} \
		-e BOOTSTRAP_ADMIN_ROLE=$${BOOTSTRAP_ADMIN_ROLE:-admin} \
		backend python -m app.scripts.bootstrap_admin
