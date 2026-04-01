# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Full-stack web application with a FastAPI Python backend, React/TypeScript frontend, and PostgreSQL database. Backend and frontend communicate via a generated OpenAPI client. All services run via Docker Compose.

## Development Commands

### Start the Stack

```bash
docker compose watch       # Development with live reload
docker compose up -d       # Production mode
docker compose down -v     # Teardown with volume cleanup
```

Local services after startup:
- Frontend: http://localhost:5173
- Backend API + Swagger UI: http://localhost:8000/docs
- Adminer (DB admin): http://localhost:8080
- MailCatcher: http://localhost:1080
- Traefik UI: http://localhost:8090

### Backend

```bash
cd backend
uv sync                                              # Install dependencies
source .venv/bin/activate                            # Activate virtualenv
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

This is also triggered automatically by pre-commit hooks. The generated client lives in `frontend/src/client/`.

## Architecture

### Service Communication

```
Browser → Traefik (proxy/SSL) → Frontend (React/Nginx) or Backend (FastAPI)
                                            Backend → PostgreSQL
```

In dev, the frontend dev server (Vite) proxies API calls to the backend at port 8000.

### Backend (`backend/app/`)

- **`main.py`** — FastAPI app creation, middleware, CORS
- **`api/main.py`** — API router aggregator (all routes under `/api/v1/`)
- **`api/routes/`** — Endpoint handlers: `login`, `users`, `items`, `utils`, `private`
- **`api/deps.py`** — Dependency injection (current user, DB session)
- **`core/config.py`** — Pydantic settings (reads from environment)
- **`core/security.py`** — JWT creation/verification, password hashing (Argon2/Bcrypt via pwdlib)
- **`models.py`** — SQLModel models shared as both ORM and Pydantic schemas
- **`crud.py`** — All database CRUD operations

Authentication uses JWT bearer tokens with 8-day expiration, stored in the frontend's localStorage.

### Frontend (`frontend/src/`)

- **`client/`** — Auto-generated Axios-based API client (do not edit manually)
- **`routes/`** — TanStack Router pages; `_layout.tsx` wraps authenticated views
- **`components/`** — Organized by domain (Admin, Items, UserSettings, Common); `ui/` contains shadcn/ui primitives
- **`hooks/`** — Custom React hooks, typically wrapping TanStack Query mutations/queries

Data fetching uses TanStack Query. Forms use React Hook Form + Zod validation.

### Data Models

Two core entities defined in `backend/app/models.py`:
- **User** — id, email, hashed_password, is_active, is_superuser, full_name
- **Item** — id, title, description, owner_id (FK to User)

SQLModel means the same class serves as both the ORM model and Pydantic request/response schema (using table/non-table variants).

### Configuration

All configuration flows through `.env` → `backend/app/core/config.py` (Pydantic `Settings`). Key variables: `SECRET_KEY`, `POSTGRES_*`, `FIRST_SUPERUSER*`, `SMTP_*`, `SENTRY_DSN`.

## Testing

- Backend tests use pytest with fixtures in `backend/tests/conftest.py`. Coverage minimum: 90%.
- Frontend E2E tests use Playwright in `frontend/`.
- CI runs backend tests, Docker Compose integration tests, and Playwright tests via GitHub Actions (`.github/workflows/`).

## Code Quality

Pre-commit hooks (configured in `.pre-commit-config.yaml`) run: Biome (frontend), Ruff (backend), MyPy (backend), and client generation. Install with:

```bash
cd backend && uv run prek install -f
```

MyPy runs in strict mode. Ruff enforces formatting and linting. Biome enforces frontend formatting/linting.
