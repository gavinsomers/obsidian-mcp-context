FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md CHANGELOG.md RELEASING.md ./
COPY obsidian_mcp_context ./obsidian_mcp_context
COPY tests ./tests
COPY examples ./examples

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -e ".[dev]"

CMD ["obsidian-mcp-context-web", "--vault", "/vault", "--host", "0.0.0.0", "--port", "8080"]
