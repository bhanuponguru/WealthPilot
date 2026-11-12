.PHONY: up down mlflow test docs docs-build

up:
	docker compose up -d postgres

down:
	docker compose down

# MLflow runs from the uv venv (single process, SQLite backend) to save RAM.
mlflow:
	uv run mlflow server --host 127.0.0.1 --port 5000 \
		--backend-store-uri sqlite:///mlflow.db \
		--default-artifact-root ./mlartifacts

test:
	uv run pytest -q

# Documentation (needs: uv sync --group docs)
docs:
	uv run mkdocs serve

docs-build:
	uv run mkdocs build --strict
