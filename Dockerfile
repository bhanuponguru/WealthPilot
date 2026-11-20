# syntax=docker/dockerfile:1.7
#
# One image runs every WealthPilot service (console, tool servers, tracking server, bootstrap job): the
# service chosen at start-up is the container command. The `lab` target adds the research package.

FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv
COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /usr/local/bin/uv
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# ---- dependencies (cached until the lock file changes)
FROM base AS deps
COPY pyproject.toml uv.lock README.md ./
COPY research/pyproject.toml research/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --no-install-workspace

# ---- the product
FROM deps AS app
COPY src ./src
COPY mcp_servers ./mcp_servers
COPY policies ./policies
COPY config ./config
COPY artifacts ./artifacts
COPY .streamlit ./.streamlit
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:${PATH}" \
    WEALTHPILOT_DATA_DIR=/data
RUN useradd --uid 1000 --create-home app \
 && mkdir -p /data /mlflow \
 && chown -R app:app /data /mlflow
USER app
EXPOSE 8501
CMD ["wealthpilot", "ui", "--host", "0.0.0.0", "--headless"]

# ---- the research package (experiments, synthetic world, reference engine)
FROM app AS lab
USER root
COPY research ./research
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --all-packages --group dev \
 && chown -R app:app /app/research
USER app
WORKDIR /app/research
CMD ["bash"]
