# AGENTS.md — LLM / Coding Agent Guide

Quick orientation for AI assistants working in this repository.

## Project

**BrightBean Studio** — multitenant social media management (Django monolith).  
Repo: https://github.com/brightbeanxyz/brightbean-studio

## Read first

1. [docs/README.md](docs/README.md) — documentation index
2. [docs/API.md](docs/API.md) — Agent API, Swagger URLs, MCP tools
3. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — stack, apps, multitenant model
4. [docs/FEATURES.md](docs/FEATURES.md) — what is API vs Web UI only

## Run locally (one command)

```bash
./scripts/start.sh          # Linux/macOS
.\scripts\start.ps1         # Windows
```

Opens:
- UI: http://localhost:8000
- **Swagger: http://localhost:8000/api/v1/docs**
- API: http://localhost:8000/api/v1/

## Critical conventions

| Topic | Rule |
|-------|------|
| **Workspace scope** | Never accept `workspace_id` in API request bodies; scope comes from bearer token |
| **Service layer** | Web UI and API share `apps/*/services.py` — change services, not duplicate logic |
| **New API endpoints** | Add Ninja router under `apps/api/routers/`, schema in `apps/api/schemas.py`, register in `apps/api/api.py` |
| **Swagger** | All Agent API routes must have `summary=` and Pydantic schemas with `Field(description=...)` |
| **Permissions** | Check via `request.workspace_membership.effective_permissions` |
| **Background jobs** | Use `@background` from `django-background-tasks`, register in app's `ready()` |
| **Platforms** | Add file in `providers/`, register in provider registry |
| **Tests** | pytest; API tests in `apps/api/tests/` |
| **Lint** | ruff + mypy (see CONTRIBUTING.md) |

## Multitenant hierarchy

```
Organization → Workspace → Members / SocialAccounts / Posts / Media
```

API keys bind to **one workspace** with an account **allowlist**.

## API surface (Swagger-documented)

Base: `/api/v1/`

| Tag | Router file | Purpose |
|-----|-------------|---------|
| `config` | `routers/config.py` | Runtime API config (dropdowns/defaults) |
| `system` | `routers/system.py` | Health (no auth) |
| `me` | `routers/me.py` | Caller introspection |
| `accounts` | `routers/accounts.py` | Allowlisted social accounts |
| `posts` | `routers/posts.py` | CRUD + schedule/cancel |
| `media` | `routers/media.py` | Upload, list, retrieve |
| `analytics` | `routers/analytics.py` | Channel + post metrics |
| `calendar` | `routers/calendar.py` | Events, queues, slots |
| `inbox` | `routers/inbox.py` | Unified inbox |
| `approvals` | `routers/approvals.py` | Approval workflow |
| `organization` | `routers/organization.py` | Org settings |
| `workspaces` | `routers/organization.py` | Workspace CRUD |
| `members` | `routers/organization.py` | Team + invitations |
| `mcp` | `apps/mcp/transport.py` | JSON-RPC MCP endpoint |

**Runtime config:** `config/api_defaults.json` + `API_CONFIG_PATH` — Swagger enums reload on container restart.

OpenAPI: `/api/v1/openapi.json`  
Disable Swagger UI: `AGENT_API_DOCS_ENABLED=false`

## Not in Agent API (Web UI only)

Client portal magic links, Kanban idea board, report builder, notifications UI, Google user SSO login — see [docs/FEATURES.md](docs/FEATURES.md).

## Common tasks

| Task | Where to look |
|------|---------------|
| Add REST endpoint | `apps/api/routers/`, `apps/api/schemas.py`, `apps/api/api.py` |
| Change publish logic | `apps/publisher/engine.py` |
| Add platform | `providers/<platform>.py` |
| RBAC permission | `apps/members/models.py` (permission registry) |
| Env var | `config/settings/base.py` + `.env.example` |
| Docker | `docker-compose.yml`, `scripts/start.*` |
| Kubernetes | `deploy/kubernetes/` |

## Do not

- Commit secrets (`.env`, credentials)
- Add `workspace_id` to API request schemas
- Skip audit logging on new authenticated API routes
- Use Celery (project uses django-background-tasks + Postgres)

## Full docs

- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — Docker, K8s, scaling
- [README.md](README.md) — platform OAuth credentials, user-facing overview
- [development_specs/](development_specs/) — original product specification
