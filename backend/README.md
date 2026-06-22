# Mykare Voice AI — Backend

Healthcare front-desk voice agent built on **LiveKit Agents 1.x**, **Groq (Llama 3.3)**, **Deepgram STT**, and **Cartesia TTS**.

## Quick start (uv)

```bash
cd backend

# Install all dependencies (creates .venv automatically)
uv sync

# Install with dev/test dependencies
uv sync --group dev

# Copy and fill in your API keys
cp .env.example .env
```

### Run the agent worker

```bash
uv run python -m agent.main dev        # dev mode — hot reload
# uv run python -m agent.main start   # production
```

### Run the API server (separate terminal)

```bash
uv run uvicorn api.server:app --host 0.0.0.0 --port 8000
```

### Pre-download VAD models (avoids first-call lag)

```bash
uv run python -m agent.main download-files
```

### Run tests

```bash
uv run pytest
uv run pytest tests/test_repository.py -v   # just the DB layer
uv run pytest tests/test_assistant.py -v    # just the agent tools
uv run pytest tests/test_api.py -v          # just the API endpoints
```

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/token?identity=<id>` | Mint a LiveKit JWT + room name |
| GET | `/appointments/{phone}` | List a caller's appointments |

## Project structure

```
backend/
├── agent/
│   ├── main.py        # AgentServer entrypoint
│   ├── assistant.py   # FrontDeskAgent + @function_tool methods
│   ├── prompts.py     # System + summary prompts
│   └── events.py      # LiveKit data channel UI events
├── api/
│   └── server.py      # FastAPI server
├── db/
│   ├── database.py    # Migration runner
│   ├── repository.py  # Async CRUD (UUID primary keys)
│   └── migrations/
│       └── 001_initial_schema.sql
├── tests/
│   ├── conftest.py    # FakeRoom + isolated DB fixtures
│   ├── test_repository.py
│   ├── test_assistant.py
│   └── test_api.py
├── pyproject.toml     # uv project + dependencies
├── .env.example
└── Dockerfile
```

## LLM stack

| Component | Provider | Model | Notes |
|-----------|----------|-------|-------|
| Conversation LLM | Groq | `llama-3.3-70b-versatile` | Free tier, no credit card |
| Post-call summary | Groq | `llama-3.3-70b-versatile` | Same key |
| STT | Deepgram | `nova-3` | Streaming |
| TTS | Cartesia | `sonic-2` | Low TTFB |
| Avatar | Beyond Presence | — | Toggle via BEY_API_KEY |

## Environment variables

See [`.env.example`](.env.example). Minimum required to run without avatar:
- `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`
- `DEEPGRAM_API_KEY`
- `CARTESIA_API_KEY`
- `GROQ_API_KEY` — free at [console.groq.com](https://console.groq.com)
