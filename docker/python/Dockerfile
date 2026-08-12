FROM python:3.12-slim AS runtime-postgres

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml readme.md changelog.md releasing.md ./
COPY obsidian_mcp_context ./obsidian_mcp_context
COPY dbt ./dbt
COPY models ./models
COPY dbt_project.yml ./

RUN python -m pip install --no-cache-dir -e .
