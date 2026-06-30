# One-click start: Web UI + Agent API + Swagger + parallel workers (Docker Compose)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker is required. Install Docker Desktop: https://www.docker.com/products/docker-desktop/"
    exit 1
}

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example"
}

$envContent = Get-Content .env -Raw
if ($envContent -match 'DATABASE_URL=postgres://postgres:postgres@localhost') {
    $envContent = $envContent -replace 'DATABASE_URL=.*', 'DATABASE_URL=postgres://postgres:postgres@postgres:5432/brightbean'
    Set-Content .env $envContent -NoNewline
}

# Generate secrets if still placeholders
python -c @"
import re, secrets
from pathlib import Path
p = Path('.env')
text = p.read_text()
for key in ('SECRET_KEY', 'ENCRYPTION_KEY_SALT'):
    if re.search(rf'^{key}=change-me', text, re.M):
        text = re.sub(rf'^{key}=.*$', f'{key}={secrets.token_urlsafe(48)}', text, flags=re.M)
p.write_text(text)
"@ 2>$null

$workerReplicas = if ($env:WORKER_REPLICAS) { $env:WORKER_REPLICAS } else { "2" }

Write-Host ""
Write-Host "Starting BrightBean Studio (multitenant UI + API + Swagger + $workerReplicas workers)..."
Write-Host ""

docker compose up -d --build --scale "worker=$workerReplicas"

Write-Host ""
Write-Host "Waiting for app health check..."
$healthy = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $null = Invoke-WebRequest -Uri "http://localhost:8000/health/" -UseBasicParsing -TimeoutSec 3
        $healthy = $true
        break
    } catch {
        Start-Sleep -Seconds 2
    }
}

Write-Host ""
Write-Host "=============================================="
Write-Host "  BrightBean Studio is running"
Write-Host "=============================================="
Write-Host "  Web UI:        http://localhost:8000"
Write-Host "  Agent API:     http://localhost:8000/api/v1/"
Write-Host "  Swagger docs:  http://localhost:8000/api/v1/docs"
Write-Host "  Health:        http://localhost:8000/health/"
Write-Host ""
Write-Host "  Multitenant:   Organization -> Workspace (built-in)"
Write-Host "  Workers:       $workerReplicas parallel background workers"
Write-Host ""
Write-Host "  Create admin:  docker compose exec app python manage.py createsuperuser"
Write-Host "  View logs:     docker compose logs -f"
Write-Host "  Stop:          docker compose down"
Write-Host "=============================================="
