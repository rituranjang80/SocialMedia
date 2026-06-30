# Feature Coverage Matrix

Maps product capabilities to integration surfaces. Use this to know whether Swagger/API covers a feature or only the Web UI.

**Legend**

| Symbol | Meaning |
|--------|---------|
| ✅ | Fully supported |
| 🔶 | Partial (subset via API/MCP) |
| 🖥️ | Web UI only |
| 🔗 | External / webhook |

---

## Multitenant & teams

| Feature | Web UI | Agent API | MCP | Notes |
|---------|--------|-----------|-----|-------|
| Organizations | 🖥️ | ✅ | — | `organization` |
| Workspaces | 🖥️ | ✅ | — | `workspaces` |
| Members & RBAC | 🖥️ | ✅ | — | `members` |
| Invitations | 🖥️ | ✅ | — | `members` |
| API keys management | 🖥️ | — | — | Create keys in UI |
| Client role / portal | 🖥️ | — | — | Magic-link client access |

Multitenant isolation: **Organization → Workspace → Members**. API keys are workspace-scoped with account allowlists.

---

## Content & publishing

| Feature | Web UI | Agent API | MCP | Swagger tag |
|---------|--------|-----------|-----|-------------|
| Compose posts | 🖥️ | ✅ | ✅ | `posts` |
| Schedule posts | 🖥️ | ✅ | ✅ | `posts` |
| Cancel scheduled | 🖥️ | ✅ | ✅ | `posts` |
| Per-platform overrides | 🖥️ | ✅ | ✅ | `posts` |
| List all posts | 🖥️ | — | — | Use UI drafts/calendar |
| Delete published | — | — | — | Never deletable (audit) |
| Idea Kanban | 🖥️ | — | — | |
| Templates & categories | 🖥️ | — | — | |
| Calendar & queues | ✅ | ✅ | — | `calendar` |
| Publishing engine | ✅ | ✅ | ✅ | Background worker |
| Parallel multi-platform publish | ✅ | ✅ | ✅ | ThreadPoolExecutor in publisher |

---

## Media library

| Feature | Web UI | Agent API | MCP | Swagger tag |
|---------|--------|-----------|-----|-------------|
| Upload | 🖥️ | ✅ | ✅ | `media` |
| List / search | 🖥️ | ✅ | ✅ | `media` |
| Folders & tags | 🖥️ | 🔶 | 🔶 | folder_id, tags on upload |
| Org shared library | 🖥️ | 🔶 | 🔶 | Visible in list if shared |
| Variants / FFmpeg | ✅ | ✅ | ✅ | Async processing |
| Unsplash stock | 🖥️ | — | — | Composer UI only |

---

## Social accounts

| Feature | Web UI | Agent API | MCP | Swagger tag |
|---------|--------|-----------|-----|-------------|
| OAuth connect | 🖥️ | 🔶 | — | `GET /accounts/connect/url` (browser completes OAuth) |
| List connected | 🖥️ | ✅ | ✅ | `accounts` |
| 10+ platforms | ✅ | ✅ | ✅ | See README platforms table |

---

## Analytics

| Feature | Web UI | Agent API | MCP | Swagger tag |
|---------|--------|-----------|-----|-------------|
| Channel KPIs | 🖥️ | ✅ | ✅ | `analytics` |
| Post metrics | 🖥️ | ✅ | ✅ | `analytics` |
| Report builder | 🖥️ | — | — | |
| Demographics | 🖥️ | — | — | UI charts |

---

## Inbox & engagement

| Feature | Web UI | Agent API | MCP |
|---------|--------|-----------|-----|
| Unified inbox | ✅ | ✅ | — | `inbox` |
| Reply to comments/DMs | ✅ | ✅ | — | `inbox` |
| Sentiment / assignment | 🖥️ | — | — |
| Platform webhooks | 🔗 | 🔗 | 🔗 | `/webhooks/*` |

---

## Approvals & clients

| Feature | Web UI | Agent API | MCP |
|---------|--------|-----------|-----|
| Approval stages | ✅ | ✅ | — | `approvals` |
| Client magic links | 🖥️ | — | — | Web portal only |
| Approval comments | 🖥️ | — | — |

---

## Notifications & settings

| Feature | Web UI | Agent API | MCP |
|---------|--------|-----------|-----|
| In-app notifications | 🖥️ | — | — |
| Email / webhook prefs | 🖥️ | — | — |
| Workspace defaults | 🖥️ | — | — |
| White-label branding | 🖥️ | — | — |

---

## Operations

| Feature | Web UI | Agent API | MCP | Swagger tag |
|---------|--------|-----------|-----|-------------|
| Health check | — | ✅ | — | `system` |
| Audit log (API) | 🖥️ | ✅ | ✅ | Automatic on API/MCP |
| Background workers | ✅ | — | — | `process_tasks` |
| Admin (Django) | 🖥️ | — | — | `/admin/` superuser |

---

## Where to go next

- **Try all API endpoints:** [Swagger UI](http://localhost:8000/api/v1/docs) (when running locally)
- **API behavior details:** [API.md](API.md)
- **Deploy & scale workers:** [DEPLOYMENT.md](DEPLOYMENT.md)
