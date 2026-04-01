# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Full-stack AI agent application with a FastAPI Python backend, React/TypeScript frontend, PostgreSQL database, and Temporal for durable workflow orchestration. The core feature is an AI-powered support ticket system where Claude analyzes tickets via a multi-step Temporal workflow.

## Development Commands

### Start the Stack

```bash
docker compose watch       # Development with live reload (recommended)
docker compose up -d       # Production mode
docker compose down -v     # Teardown with volume cleanup
```

Local services after startup:
- Frontend: http://localhost:5173
- Backend API + Swagger UI: http://localhost:8000/docs
- Adminer (DB admin): http://localhost:8080
- MailCatcher: http://localhost:1080
- Traefik UI: http://localhost:8090
- Temporal UI: http://localhost:8233

### Temporal Worker (separate terminal — required for ticket processing)

```bash
cd backend
uv run python -m app.worker
```

The worker must run as a separate process. It connects to Temporal at `localhost:7233`, registers `TicketWorkflow` and all activities, and polls the `ticket-processing` task queue.

### Backend

```bash
cd backend
uv sync                                              # Install dependencies
fastapi dev app/main.py                              # Run locally (with reload)
bash ./scripts/test.sh                               # Run tests
docker compose exec backend bash scripts/tests-start.sh  # Run tests in stack
ruff check && ruff format                            # Lint + format
mypy backend/app                                     # Type check
```

Database migrations:
```bash
alembic revision --autogenerate -m "description"     # Create migration
alembic upgrade head                                  # Apply migrations
```

### Frontend

```bash
cd frontend
bun install                    # Install dependencies
bun run dev                    # Dev server (http://localhost:5173)
bun run build                  # Production build
bun run lint                   # Lint with Biome
bun run test                   # E2E tests (Playwright)
bun run test:ui                # Playwright UI mode
bun run generate-client        # Regenerate OpenAPI client from backend schema
```

### Generate Frontend API Client

Run after changing backend routes:
```bash
bash ./scripts/generate-client.sh
```

Generated client lives in `frontend/src/client/`.

## Architecture

### Service Communication

```
Browser → Traefik (proxy/SSL) → Frontend (React/Nginx) or Backend (FastAPI)
                                            Backend → PostgreSQL
                                            Backend → Temporal Server
                                            Worker  → Temporal Server
                                            Worker  → Anthropic API
```

In dev, the frontend dev server (Vite) proxies API calls to the backend at port 8000.

### Backend (`backend/app/`)

- **`main.py`** — FastAPI app creation, middleware, CORS
- **`api/main.py`** — API router aggregator (all routes under `/api/v1/`)
- **`api/routes/`** — Endpoint handlers: `login`, `users`, `items`, `utils`, `tickets`
- **`api/deps.py`** — Dependency injection (current user, DB session, Temporal client)
- **`core/config.py`** — Pydantic settings (reads from environment)
- **`core/security.py`** — JWT creation/verification, password hashing
- **`models.py`** — SQLModel models: User, Item, Ticket, TicketAnalysis
- **`crud.py`** — Database CRUD operations
- **`worker.py`** — Temporal worker entry point (run separately)

### Temporal Layer (`backend/app/`)

- **`workflows/ticket_workflow.py`** — Defines the 7-step pipeline and execution order
- **`activities/ticket_activities.py`** — Implementations of each workflow step
- **`agents/investigation_agent.py`** — Claude agentic loop using Anthropic SDK tool_runner
- **`tools/ticket_tools.py`** — Tool implementations (knowledge base search, similar ticket lookup)

### Ticket Workflow Pipeline

```
fetch_ticket → classify_ticket → decide_action
  └─ if "investigate":
       get_similar_tickets → run_investigation_agent → validate_result
  └─ if "auto_resolve":
       (skip to validate with canned response)
→ update_ticket → respond_to_user
```

The workflow is defined in `ticket_workflow.py`. Activities in `ticket_activities.py` are just implementations — order is irrelevant there.

### Investigation Agent

Uses the **Anthropic SDK beta tool runner** (`@beta_tool` + `client.beta.messages.tool_runner()`). Tools are defined as decorated functions with closures — no hand-written JSON schemas or manual message loop.

- Model: `claude-opus-4-6` for investigation, `claude-haiku-4-5` for classification
- Tools: `search_knowledge_base`, `get_similar_tickets`, `submit_analysis`
- The tool_runner is synchronous; called via `asyncio.to_thread` from the async Temporal activity

### Frontend (`frontend/src/`)

- **`client/`** — Auto-generated Axios-based API client (do not edit manually)
- **`routes/`** — TanStack Router pages; `_layout.tsx` wraps authenticated views
- **`routes/_layout/tickets.tsx`** — Ticket submission and live status polling
- **`components/`** — Organized by domain; `ui/` contains shadcn/ui primitives
- **`hooks/`** — Custom React hooks wrapping TanStack Query

### Data Models

Defined in `backend/app/models.py`:
- **User** — id, email, hashed_password, is_active, is_superuser, full_name
- **Item** — id, title, description, owner_id (FK to User)
- **Ticket** — id, title, description, status, owner_id, created_at
- **TicketAnalysis** — ticket_id, summary, diagnosis, suggested_fix, priority, needs_human, confidence

### Configuration

All configuration flows through `.env` → `backend/app/core/config.py`. Key variables:
- `SECRET_KEY`, `POSTGRES_*`, `FIRST_SUPERUSER*`, `SMTP_*` — standard app config
- `ANTHROPIC_API_KEY` — required for Claude API calls in the worker
- `TEMPORAL_HOST` — defaults to `localhost:7233` (worker); overridden to `temporal:7233` for the backend container in `compose.override.yml`
- `TEMPORAL_TASK_QUEUE` — defaults to `ticket-processing`

### Important: docker compose watch vs worker

`docker compose watch` auto-syncs Python file changes into the backend container — no restart needed for backend edits. The **worker** (local terminal) does NOT have watch — restart it manually after any Python change.

## Testing

- Backend tests use pytest with fixtures in `backend/tests/conftest.py`. Coverage minimum: 90%.
- Frontend E2E tests use Playwright in `frontend/`.
- CI runs backend tests, Docker Compose integration tests, and Playwright tests via GitHub Actions (`.github/workflows/`).

## Code Quality

Pre-commit hooks (configured in `.pre-commit-config.yaml`) run: Biome (frontend), Ruff (backend), MyPy (backend), and client generation. Install with:

```bash
cd backend && uv run pre-commit install -f
```

MyPy runs in strict mode. Ruff enforces formatting and linting. Biome enforces frontend formatting/linting.
