# Agent API Reference

BrightBean Studio's **programmatic API** for AI agents and integrations. All REST endpoints below are documented in **Swagger** and share one OpenAPI schema.

## Swagger & OpenAPI

| Resource | URL |
|----------|-----|
| **Swagger UI** (interactive) | `{APP_URL}/api/v1/docs` |
| **OpenAPI JSON** | `{APP_URL}/api/v1/openapi.json` |
| **Local default** | http://localhost:8000/api/v1/docs |

Toggle Swagger: `AGENT_API_DOCS_ENABLED=true|false` in `.env`.

Every request field, response shape, and error code is defined in the OpenAPI spec. **Prefer Swagger as the source of truth** for request/response schemas; this document explains behavior, auth, and how endpoints relate to product features.

---

## Authentication

All endpoints except **system** require a bearer token:

```http
Authorization: Bearer bb_studio_<your_api_key>
```

### Create an API key

1. Sign in to the Web UI
2. Go to **Organization → Settings → API Keys** (`/organizations/api-keys/`)
3. Create a key with:
   - Target **workspace**
   - Allowed **social accounts** (allowlist)
   - **Permissions** (e.g. `create_posts`, `view_analytics`, `upload_media`)

The key is bound to one workspace. You cannot override workspace scope in request bodies (confused-deputy protection).

### MCP / Claude Desktop

`/api/v1/mcp` also accepts **OAuth 2.1** access tokens from the built-in authorization server (`/oauth/*`). See [OAuth & MCP](#oauth--mcp) below.

---

## Rate limits

| Tier | Write | Read |
|------|-------|------|
| Per API key | 120/min | 300/min |
| Per workspace (aggregate) | — | 1000/min cap |

- **429** responses include `tier`, `limit`, `remaining`, `retry_after`, and `Retry-After` header
- **Per-platform daily caps** also apply when posting (e.g. Instagram 25/day) — 429 with `retry_after` until oldest post ages out

---

## Runtime configuration (no rebuild)

Swagger dropdowns, default query values, and pagination limits are **not hardcoded**. They load from:

| Source | Purpose |
|--------|---------|
| `config/api_defaults.json` | Default bundled config |
| `API_CONFIG_PATH` | Override path (mount in Docker/K8s) |
| `API_INBOX_DEFAULT_LIMIT`, etc. | Per-env overrides (see `.env.example`) |

| Method | Path | Auth |
|--------|------|------|
| `GET` | `/config/` | None |

After editing the JSON file: **restart** the app container — no image rebuild.

Docker Compose mounts `./config/api_defaults.json` → `/app/config/api_runtime.json` by default.

---

## REST endpoints (Swagger tags)

Base path: `/api/v1`

### `system` — no auth

| Method | Path | Summary |
|--------|------|---------|
| `GET` | `/system/health` | Liveness probe (`{"status":"ok"}`) |

Also available outside the API namespace: `GET /health/`

### `me`

| Method | Path | Summary |
|--------|------|---------|
| `GET` | `/me/` | Caller scope: workspace, permissions, storage quota, allowlisted accounts |

### `accounts` (incl. OAuth connect)

| Method | Path | Summary | Permission |
|--------|------|---------|------------|
| `GET` | `/accounts/` | List allowlisted accounts | — |
| `GET` | `/accounts/connect/options` | Platforms available to connect | `manage_social_accounts` |
| `GET` | `/accounts/connect/url?platform=` | Browser OAuth connect URL | `manage_social_accounts` |
| `GET` | `/accounts/{id}` | Account detail + connection status | allowlist |
| `POST` | `/accounts/{id}/disconnect` | Disconnect account | `manage_social_accounts` |

OAuth token exchange remains browser-based; the API returns the Web UI connect URL to open in a logged-in session.

### `calendar`

| Method | Path | Permission |
|--------|------|------------|
| `GET` | `/calendar/events` | membership |
| `POST` | `/calendar/reschedule` | `edit_others_posts` or own post |
| `GET` | `/calendar/queues` | membership |
| `POST` | `/calendar/queues/{id}/entries` | `create_posts` |
| `DELETE` | `/calendar/queues/{id}/entries/{entry_id}` | `create_posts` |
| `GET` | `/calendar/posting-slots` | `manage_social_accounts` |
| `GET/POST` | `/calendar/custom-events` | `create_posts` |

### `inbox`

| Method | Path | Permission |
|--------|------|------------|
| `GET` | `/inbox/messages` | `use_inbox` |
| `GET` | `/inbox/messages/{id}` | `use_inbox` |
| `POST` | `/inbox/messages/{id}/reply` | `reply_from_inbox` |
| `POST` | `/inbox/messages/{id}/notes` | `reply_from_inbox` |
| `PATCH` | `/inbox/messages/{id}` | `reply_from_inbox` |
| `POST` | `/inbox/messages/bulk` | `reply_from_inbox` |
| `GET/POST` | `/inbox/saved-replies` | `manage_workspace_settings` |
| `GET/PUT` | `/inbox/sla-config` | `manage_workspace_settings` |

### `approvals`

| Method | Path | Permission |
|--------|------|------------|
| `GET` | `/approvals/queue` | `approve_posts` |
| `POST` | `/approvals/posts/{id}/submit` | `create_posts` |
| `POST` | `/approvals/posts/{id}/approve` | `approve_posts` |
| `POST` | `/approvals/posts/{id}/request-changes` | `approve_posts` |
| `POST` | `/approvals/posts/{id}/reject` | `approve_posts` |
| `POST` | `/approvals/posts/{id}/resubmit` | `create_posts` |
| `POST` | `/approvals/bulk/approve` | `approve_posts` |
| `POST` | `/approvals/bulk/reject` | `approve_posts` |
| `GET/PUT` | `/approvals/settings` | read / `manage_workspace_settings` |

### `organization` / `workspaces` / `members`

Requires API key **issuer** to hold org role (not just workspace permissions).

| Tag | Method | Path | Org role |
|-----|--------|------|----------|
| `organization` | `GET/PATCH` | `/organization/` | member / admin |
| `workspaces` | `GET` | `/workspaces/` | member |
| `workspaces` | `POST` | `/workspaces/` | admin |
| `workspaces` | `GET/PATCH` | `/workspaces/current` | membership / `manage_workspace_settings` |
| `members` | `GET` | `/members/` | member |
| `members` | `POST` | `/members/invitations` | admin |
| `members` | `PATCH/DELETE` | `/members/{id}/…` | admin |

Returns `char_limit`, `needs_title`, `supports_first_comment` on account endpoints — check before composing posts.

### `posts`

| Method | Path | Summary | Permission |
|--------|------|---------|------------|
| `POST` | `/posts/` | Create draft or scheduled post | `create_posts` |
| `GET` | `/posts/{post_id}` | Read single post | `view_posts` |
| `PATCH` | `/posts/{post_id}` | Update draft fields | `edit_posts` |
| `POST` | `/posts/{post_id}/schedule` | Schedule a draft | `schedule_posts` |
| `POST` | `/posts/{post_id}/cancel` | Cancel scheduled → draft | `schedule_posts` |

**Not in v1 API:** list all posts, delete published posts. Use the Web UI for drafts list; published posts are immutable audit records.

**Idempotency:** Pass `Idempotency-Key` header on writes to safely retry.

### `media`

| Method | Path | Summary | Permission |
|--------|------|---------|------------|
| `POST` | `/media/` | Upload file (`multipart/form-data`) | `upload_media` |
| `GET` | `/media/` | List assets (filters, cursor pagination) | `view_media` |
| `GET` | `/media/{media_id}` | Retrieve single asset | `view_media` |

Default list filter: `processing_status=completed` so agents don't reference in-flight uploads.

### `analytics`

| Method | Path | Summary | Permission |
|--------|------|---------|------------|
| `GET` | `/analytics/accounts/{account_id}?days=7-90` | Channel KPIs + trends | `view_analytics` |
| `GET` | `/analytics/posts/{post_id}` | Per-platform post metrics | `view_analytics` |

### `mcp`

| Method | Path | Summary |
|--------|------|---------|
| `POST` | `/mcp` | MCP Streamable HTTP (JSON-RPC 2.0) |

Auth: `bb_studio_` key **or** OAuth 2.1 bearer.

#### MCP tools (call via `tools/call`)

| Tool | REST equivalent |
|------|-----------------|
| `list_accounts` | `GET /accounts/` |
| `create_draft` | `POST /posts/` (draft) |
| `schedule_post` | `POST /posts/` + schedule |
| `schedule_draft` | `POST /posts/{id}/schedule` |
| `get_post` | `GET /posts/{id}` |
| `cancel_post` | `POST /posts/{id}/cancel` |
| `search_media` | `GET /media/` |
| `get_media` | `GET /media/{id}` |
| `upload_media` | `POST /media/` (base64, ≤5 MB) |
| `request_media_upload` | Presigned upload flow (large files) |
| `finalize_media_upload` | Complete presigned upload |
| `get_account_analytics` | `GET /analytics/accounts/{id}` |
| `get_post_analytics` | `GET /analytics/posts/{id}` |

Discover tools at runtime: JSON-RPC `tools/list` on `/api/v1/mcp`.

---

## OAuth & MCP

For native MCP clients (e.g. Claude Desktop):

| Endpoint | Purpose |
|----------|---------|
| `GET /.well-known/oauth-authorization-server` | OAuth server metadata |
| `GET /.well-known/oauth-protected-resource/api/v1/mcp` | Resource metadata (RFC 9728) |
| `POST /oauth/register` | Dynamic Client Registration |
| `GET /oauth/authorize/` | Authorization code + PKCE |
| `POST /oauth/token/` | Token exchange |
| `POST /oauth/revoke_token/` | Revoke token |

Env: `MCP_PUBLIC_BASE_URL`, `MCP_OAUTH_ISSUER_URL` (default to `APP_URL`).

---

## Inbound webhooks (platform → Studio)

Not in Swagger — called by Meta, YouTube, etc.

| Path | Platform |
|------|----------|
| `POST /webhooks/facebook/` | Facebook |
| `POST /webhooks/instagram_login/` | Instagram Login |
| `POST /webhooks/youtube/` | YouTube |

Configure verify tokens via `.env`: `FACEBOOK_WEBHOOK_VERIFY_TOKEN`, `INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN`, `YOUTUBE_WEBHOOK_SECRET`.

---

## Error envelope

Authenticated failures use a consistent JSON shape:

```json
{
  "error": "rate_limited",
  "detail": "...",
  "tier": "per_key",
  "limit": 120,
  "remaining": 0,
  "retry_after": 42
}
```

Common `error` values: `unauthorized`, `forbidden`, `not_found`, `rate_limited`, `storage_quota_exceeded`, `unprocessable_entity`.

All authenticated requests are **audit-logged** (action + status code).

---

## Typical agent workflow

1. `GET /me/` — confirm workspace, permissions, storage
2. `GET /accounts/` — pick target accounts, check `char_limit` / `supports_first_comment`
3. `POST /media/` — upload assets (if needed)
4. `POST /posts/` — create draft with per-platform captions
5. `POST /posts/{id}/schedule` — schedule publish time
6. Poll `GET /posts/{id}` until status is `published`
7. `GET /analytics/posts/{id}` — read performance

Use **Swagger** at `/api/v1/docs` to explore request bodies and try calls with your bearer token.

---

## Web UI only

These remain browser-only (no REST equivalent):

- Drag-and-drop calendar UI polish (reschedule API exists)
- Client portal magic-link flows
- Kanban idea board, report builder
- Google SSO user login (distinct from platform OAuth connect URLs)

See [FEATURES.md](FEATURES.md) for the full matrix.
