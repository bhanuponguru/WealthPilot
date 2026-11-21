.PHONY: up down build logs ps doctor demo-data lab test test-live test-live-docker docs docs-build dev-services mlflow ui

# ---- Deployment (Docker Compose)
up:
	docker compose up -d --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f --tail 100

ps:
	docker compose ps

doctor:
	docker compose exec console wealthpilot doctor

# Generate the optional demonstration data (sample applicants, statements, mock sources) into the data volume.
# Then start the stack with WEALTHPILOT_DEMO=1 to show sample applicants on the New case page.
demo-data:
	docker compose --profile lab run --rm lab sh -c "python -m wealthpilot_lab.synth.applicants && python -m wealthpilot_lab.synth.news && python -m wealthpilot_lab.synth.render_docs"

# Shell in the research container (experiments, reference engine, ground truth)
lab:
	docker compose --profile lab run --rm lab

# ---- Local development (without containers for the application itself)
# The database comes from Compose; run Ollama on the host (`ollama pull nomic-embed-text`) and the tool servers with `uv run wealthpilot mcp-up`.
dev-services:
	docker compose up -d postgres

mlflow:
	uv run mlflow server --host 127.0.0.1 --port 5000 \
		--backend-store-uri sqlite:///mlflow.db \
		--default-artifact-root ./mlartifacts

ui:
	uv run wealthpilot ui

test:
	uv run pytest -q -m "not live"

test-live:
	uv run pytest -q -m live

# The same live tests, run inside the Compose network against the deployed services (the stack must be up and
# demonstration data generated with `make demo-data`; restart mcp and console afterwards).
test-live-docker:
	docker compose --profile lab run --rm -e WEALTHPILOT_DEMO=1 -v "$(CURDIR)/tests:/app/tests:ro" -v "$(CURDIR)/pyproject.toml:/app/pyproject.toml:ro" \
	  lab python -m pytest -q -m live -p no:cacheprovider --rootdir /app -c /app/pyproject.toml /app/tests

# ---- Documentation (needs: uv sync --group docs)
docs:
	uv run mkdocs serve

docs-build:
	uv run mkdocs build --strict
