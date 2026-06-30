# BrightBean Studio Documentation

Central index for humans and LLMs. Start here to understand the codebase, APIs, and deployment.
rituranjan.gupta@gmail.com/H@ppy_123
## Quick links

| Topic | Document | When to read |
|-------|----------|--------------|
| **Agent API + Swagger** | [API.md](API.md) | Programmatic access, OpenAPI, MCP tools, auth, rate limits |
| **Feature coverage** | [FEATURES.md](FEATURES.md) | What is REST/MCP vs Web UI only |
| **Deploy (Docker / K8s)** | [DEPLOYMENT.md](DEPLOYMENT.md) | One-click run, production, scaling workers |
| **Architecture** | [ARCHITECTURE.md](ARCHITECTURE.md) | Stack, multitenant model, apps, data flow |
| **LLM / agent orientation** | [../AGENTS.md](../AGENTS.md) | Short context for coding agents |

## Live Swagger (when server is running)

| URL | Purpose |
|-----|---------|
| `http://localhost:8000/api/v1/docs` | Interactive Swagger UI — try all Agent API endpoints |
| `http://localhost:8000/api/v1/openapi.json` | Machine-readable OpenAPI 3 schema |
| `http://localhost:8000/health/` | Public health check (also `GET /api/v1/system/health` in Swagger) |

Set `AGENT_API_DOCS_ENABLED=false` in production to hide Swagger UI.

## Repository map

```
brightbean-studio/
├── apps/                    # Django applications (domain logic)
│   ├── api/                 # Agent REST API (Ninja) — Swagger documented
│   ├── mcp/                 # MCP transport + tools (also under /api/v1/mcp)
│   ├── organizations/       # Multitenant: org level
│   ├── workspaces/          # Multitenant: workspace level
│   ├── composer/            # Post editor (Web UI + services used by API)
│   ├── publisher/           # Background publishing engine
│   └── …                    # inbox, analytics, approvals, media_library, etc.
├── config/                  # Django settings, root urls.py
├── providers/               # Per-platform social API integrations
├── deploy/kubernetes/       # Kubernetes manifests
├── scripts/                 # One-click start scripts (Docker, K8s)
├── docs/                    # This documentation set
└── development_specs/       # Original product + architecture specs (detailed)
```

## Surfaces at a glance

BrightBean Studio exposes **three** integration surfaces:

1. **Web UI** — Django templates + HTMX at `/` (human users, full feature set)
2. **Agent REST API** — `/api/v1/*` with **Swagger** at `/api/v1/docs`
3. **MCP** — `/api/v1/mcp` (JSON-RPC; tools mirror REST capabilities for AI clients)

OAuth 2.1 (`/oauth/*`) and inbound webhooks (`/webhooks/*`) are documented in [API.md](API.md) but are not part of the Swagger spec.

## Related files in repo root

- [README.md](../README.md) — Project overview, quick start, platform credentials
- [CONTRIBUTING.md](../CONTRIBUTING.md) — Dev workflow, tests, code style
- [SECURITY.md](../SECURITY.md) — Vulnerability reporting, self-host hardening
- [development_specs/](../development_specs/) — Full product spec and original architecture notes
