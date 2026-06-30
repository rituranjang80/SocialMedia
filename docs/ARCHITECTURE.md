# Architecture Overview

LLM-friendly summary of how BrightBean Studio is built. For the full original spec see `development_specs/architecture.md` and `development_specs/feature-spec-social-media-management-v2.md`.

## What this project is

Open-source, self-hostable **social media management** platform. Multitenant SaaS shape: agencies manage many client workspaces from one deployment.

**Users interact via:**
- Web dashboard (primary, full features)
- Agent REST API + Swagger (`/api/v1/docs`)
- MCP for AI clients (`/api/v1/mcp`)

## Stack

| Layer | Technology |
|-------|------------|
| Backend | Django 5.x, Python 3.12+ |
| API | Django Ninja (OpenAPI / Swagger) |
| Frontend | Django templates, HTMX, Alpine.js |
| CSS | Tailwind CSS 4 (django-tailwind) |
| Database | PostgreSQL 16+ |
| Jobs | django-background-tasks (Postgres queue, no Redis required) |
| Media | Local filesystem or S3-compatible |
| Video | FFmpeg; images: Pillow |
| Production HTTP | Gunicorn (+ Caddy for HTTPS in Docker prod) |

## Multitenant model

```
Organization (tenant root)
  └── Workspace (client / brand)
        └── Members (RBAC: owner, admin, editor, client, custom roles)
        └── SocialAccounts (OAuth-connected platforms)
        └── Posts, Media, Calendar, Inbox, Analytics, …
```

- **v1:** one org per user (middleware uses `.first()` on org membership)
- **Isolation:** `RBACMiddleware` + scoped Django managers + API key workspace binding
- **API keys:** issued per workspace with social-account allowlist and permission set

## Request flow (Web UI)

```
HTTP → SecurityMiddleware → WhiteNoise → Session → CSRF
     → Auth → RBACMiddleware (org + workspace from URL)
     → View (Django) → Template + HTMX partial
```

## Request flow (Agent API)

```
HTTP → … → ApiKeyAuth (resolves workspace + virtual membership)
     → Ninja router → Service layer (composer, media_library, analytics)
     → Audit log + idempotency (writes)
```

Swagger schema auto-generated from Pydantic schemas in `apps/api/schemas.py`.

## Background processing

Single management command: `python manage.py process_tasks`

Polls Postgres `background_task` table. Registered recurring tasks on `post_migrate`:

| Task domain | App | Purpose |
|-------------|-----|---------|
| Publishing | `apps.publisher` | Schedule → publish (parallel per platform) |
| Inbox sync | `apps.inbox` | Poll platform APIs for messages |
| Analytics | `apps.analytics` | Snapshot metrics |
| Media | `apps.media_library` | FFmpeg transcodes |
| Notifications | `apps.notifications` | Async delivery |
| Intelligence | `apps.intelligence` | Optional SaaS integration |

**Parallel publishing:** `ThreadPoolExecutor` in `apps/publisher/engine.py` — configurable via `PUBLISHER_MAX_CONCURRENT_*` env vars.

Scale horizontally: multiple `worker` containers/processes (Docker `--scale`, K8s replicas).

## Social providers

`providers/` — one module per platform implementing `SocialProvider` abstract interface.

```
providers/base.py → facebook, instagram, linkedin, tiktok, youtube,
                    pinterest, threads, bluesky, google_business, mastodon
```

No third-party aggregator. Direct first-party API calls with deployer's credentials.

## Django apps (domain map)

| App | Responsibility |
|-----|----------------|
| `accounts` | User auth, sessions, Google SSO |
| `organizations` | Org settings, deletion workflow |
| `workspaces` | Workspace CRUD, branding |
| `members` | RBAC, invitations, middleware |
| `social_accounts` | OAuth flows, account metadata |
| `composer` | Posts, platform variants, drafts |
| `calendar` | Scheduling UI, queues, slots |
| `publisher` | Publish engine, retries, rate limits |
| `media_library` | Assets, folders, quotas, transcoding |
| `inbox` | Unified inbox, webhooks |
| `analytics` | Metrics from platform APIs |
| `approvals` | Workflow stages, comments |
| `client_portal` | Magic-link client access |
| `notifications` | In-app, email, webhooks |
| `api` | Agent REST API (Swagger) |
| `api_keys` | Key issuance UI |
| `mcp` | MCP transport + tool handlers |
| `oauth_server` | OAuth 2.1 for MCP clients |
| `credentials` | Encrypted platform API credentials |

## API vs UI boundary

- **Service layer** (`apps/composer/services.py`, `apps/media_library/services.py`) is shared between Web UI and Agent API
- **Agent API** exposes a focused subset for programmatic agents (posts, media, analytics, accounts)
- **Web UI** covers full product (calendar, inbox, approvals, settings, OAuth connect)

See [FEATURES.md](FEATURES.md) for the complete matrix.

## Key files

| File | Role |
|------|------|
| `config/urls.py` | Root URL routing |
| `config/settings/base.py` | Shared settings + env vars |
| `apps/api/api.py` | NinjaAPI instance, Swagger, error handlers |
| `apps/publisher/engine.py` | Publish loop + parallelism |
| `docker-compose.yml` | Local/prod container orchestration |
| `deploy/kubernetes/` | K8s manifests |

## Settings modules

| Module | Used when |
|--------|-----------|
| `config.settings.development` | `manage.py runserver`, Docker dev override |
| `config.settings.production` | Gunicorn, Docker prod, K8s |
| `config.settings.test` | pytest |

## Data stores

- **PostgreSQL:** all relational data + job queue
- **Media:** `MEDIA_ROOT` or S3 (`STORAGE_BACKEND=s3`)
- **Redis:** optional, not required (future real-time features)

## Security highlights

- Encrypted OAuth tokens (`ENCRYPTION_KEY_SALT`)
- API key allowlist (no cross-account confused deputy)
- CSP + nonce for Swagger in production
- Org/workspace scoped queries in middleware
- Audit log on all Agent API / MCP calls

See [SECURITY.md](../SECURITY.md).
