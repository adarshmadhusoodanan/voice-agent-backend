#!/bin/bash
set -e

# Start the LiveKit agent worker in background
uv run python -m agent.main start &

# Start the FastAPI server in foreground — Render binds $PORT to this process
exec uv run uvicorn api.server:app --host 0.0.0.0 --port "${PORT:-8000}"
