FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Install dependencies first — cached unless pyproject.toml or uv.lock changes
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

# Copy source
COPY . .
RUN chmod +x ./start.sh

# Default: run both API + agent (used on Render and locally via docker run)
CMD ["./start.sh"]
