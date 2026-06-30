#!/usr/bin/env bash
# One-click start: Web UI + Agent API + Swagger + parallel workers (Docker Compose)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required. Install Docker Desktop: https://www.docker.com/products/docker-desktop/"
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

# Ensure Docker-internal database URL
if grep -q '^DATABASE_URL=postgres://postgres:postgres@localhost' .env 2>/dev/null; then
  sed -i.bak 's|^DATABASE_URL=.*|DATABASE_URL=postgres://postgres:postgres@postgres:5432/brightbean|' .env
  rm -f .env.bak
fi

# Generate secrets if still placeholders
python3 - <<'PY' 2>/dev/null || python - <<'PY'
import re, secrets
from pathlib import Path
p = Path(".env")
text = p.read_text()
for key in ("SECRET_KEY", "ENCRYPTION_KEY_SALT"):
    if re.search(rf"^{key}=change-me", text, re.M):
        text = re.sub(rf"^{key}=.*$", f"{key}={secrets.token_urlsafe(48)}", text, flags=re.M)
p.write_text(text)
PY

WORKER_REPLICAS="${WORKER_REPLICAS:-2}"
export WORKER_REPLICAS

echo ""
echo "Starting BrightBean Studio (multitenant UI + API + Swagger + $WORKER_REPLICAS workers)..."
echo ""

docker compose up -d --build --scale "worker=${WORKER_REPLICAS}"

echo ""
echo "Waiting for app health check..."
for i in $(seq 1 60); do
  if curl -sf http://localhost:8000/health/ >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo ""
echo "=============================================="
echo "  BrightBean Studio is running"
echo "=============================================="
echo "  Web UI:        http://localhost:8000"
echo "  Agent API:     http://localhost:8000/api/v1/"
echo "  Swagger docs:  http://localhost:8000/api/v1/docs"
echo "  Health:        http://localhost:8000/health/"
echo ""
echo "  Multitenant:   Organization -> Workspace (built-in)"
echo "  Workers:       ${WORKER_REPLICAS} parallel background workers"
echo ""
echo "  Create admin:  docker compose exec app python manage.py createsuperuser"
echo "  View logs:     docker compose logs -f"
echo "  Stop:          docker compose down"
echo "=============================================="
