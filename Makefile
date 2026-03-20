.PHONY: up down logs restart build migrate seed test lint fmt shell db-shell

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f app

restart:
	docker compose restart app

build:
	docker compose build app

migrate:
	docker compose exec app alembic upgrade head

migrate-new:
	docker compose exec app alembic revision --autogenerate -m "$(msg)"

seed:
	docker compose exec app python -m scripts.seed

test:
	docker compose exec app pytest -x -v

test-local:
	pytest -x -v --tb=short

lint:
	ruff check app/ tests/

fmt:
	ruff format app/ tests/

shell:
	docker compose exec app python -c "from app.database import *; import asyncio"

db-shell:
	docker compose exec db psql -U masterbot masterbot

health:
	curl -s http://localhost:8000/health | python -m json.tool

dev:
	uvicorn app.main:create_app --factory --reload --host 0.0.0.0 --port 8000
