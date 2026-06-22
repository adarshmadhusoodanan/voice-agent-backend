FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Install dependencies first — cached unless pyproject.toml or uv.lock changes
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

# Copy source
COPY . .

# Pre-download VAD and turn-detector models to avoid cold-start lag
RUN uv run python -m agent.main download-files || true

# Default command (overridden per-service in docker-compose.yml)
CMD ["uv", "run", "python", "-m", "agent.main", "start"]
