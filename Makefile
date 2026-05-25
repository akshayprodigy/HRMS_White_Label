.PHONY: help build up down restart logs migrate test shell ui-test up-prod down-prod logs-prod seed-departments

help:
	@echo "Available commands:"
	@echo "  build    - Build docker images"
	@echo "  up       - Start the development stack (rebuild)"
	@echo "  down     - Stop the development stack"
	@echo "  restart  - Restart the development stack"
	@echo "  logs     - Tail docker logs"
	@echo "  migrate  - Run database migrations"
	@echo "  seed-departments - Seed master departments (Engineering, HR, Accounts, …)"
	@echo "  test     - Run backend tests"
	@echo "  ui-test  - Run UI tests (visible browser)"
	@echo "  shell    - Open a shell in the backend container"
	@echo "  up-prod  - Start the production stack (rebuild)"
	@echo "  down-prod- Stop the production stack"
	@echo "  logs-prod- Tail production logs"

build:
	docker compose build

up:
	docker compose up -d --build

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

migrate:
	docker compose exec backend alembic upgrade head

seed-departments:
	docker compose exec backend python -m scripts.seed_departments

test:
	docker compose exec backend pytest

ui-test:
	bash scripts/run_ui_tests.sh

shell:
	docker compose exec backend /bin/bash

up-prod:
	docker compose -f docker-compose.prod.yml up -d --build

down-prod:
	docker compose -f docker-compose.prod.yml down

logs-prod:
	docker compose -f docker-compose.prod.yml logs -f
