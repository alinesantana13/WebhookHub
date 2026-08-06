.PHONY: install run lint format typecheck test migrate migration-check check compose-up compose-down

install:
	uv sync --project backend --group dev

run:
	uv run --project backend uvicorn webhookhub.main:app --reload

lint:
	uv run --project backend ruff check backend

format:
	uv run --project backend ruff format backend

typecheck:
	uv run --project backend mypy backend/src backend/tests

test:
	uv run --project backend pytest backend/tests

migrate:
	uv run --project backend alembic -c backend/alembic.ini upgrade head

migration-check:
	uv run --project backend alembic -c backend/alembic.ini check

check: lint typecheck test

compose-up:
	docker compose up --build

compose-down:
	docker compose down
