# One-click Kubernetes deploy: build image, apply manifests, port-forward UI + API
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) {
    Write-Host "kubectl is required. Install: https://kubernetes.io/docs/tasks/tools/"
    exit 1
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker is required to build the application image."
    exit 1
}

$Image = if ($env:BRIGHTBEAN_IMAGE) { $env:BRIGHTBEAN_IMAGE } else { "brightbean-studio:latest" }
$workerReplicas = if ($env:WORKER_REPLICAS) { $env:WORKER_REPLICAS } else { "2" }

Write-Host "Building Docker image: $Image"
docker build -t $Image .

function New-RandomSecret {
    python -c "import secrets; print(secrets.token_urlsafe(48))"
}

$secretKey = if ($env:SECRET_KEY) { $env:SECRET_KEY } else { New-RandomSecret }
$encryptionSalt = if ($env:ENCRYPTION_KEY_SALT) { $env:ENCRYPTION_KEY_SALT } else { New-RandomSecret }

$overlayDir = Join-Path $env:TEMP ("brightbean-k8s-" + [guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $overlayDir | Out-Null

$imageName, $imageTag = $Image -split ":", 2
if (-not $imageTag) { $imageTag = "latest" }

@"

apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - $($Root.Replace('\', '/'))/deploy/kubernetes
secretGenerator:
  - name: brightbean-studio-secrets
    behavior: replace
    literals:
      - SECRET_KEY=$secretKey
      - ENCRYPTION_KEY_SALT=$encryptionSalt
patches:
  - target:
      kind: Deployment
      name: brightbean-worker
    patch: |-
      - op: replace
        path: /spec/replicas
        value: $workerReplicas
images:
  - name: brightbean-studio
    newName: $imageName
    newTag: $imageTag
"@ | Set-Content (Join-Path $overlayDir "kustomization.yaml")

Write-Host "Applying Kubernetes manifests..."
kubectl apply -k $overlayDir

Write-Host "Waiting for postgres..."
kubectl -n brightbean-studio wait --for=condition=ready pod -l app.kubernetes.io/component=postgres --timeout=180s

Write-Host "Running database migrations..."
kubectl -n brightbean-studio delete job brightbean-migrate --ignore-not-found
kubectl -n brightbean-studio apply -f (Join-Path $Root "deploy\kubernetes\migrate-job.yaml")
kubectl -n brightbean-studio wait --for=condition=complete job/brightbean-migrate --timeout=300s

Write-Host "Waiting for app deployment..."
kubectl -n brightbean-studio rollout status deployment/brightbean-app --timeout=300s
kubectl -n brightbean-studio rollout status deployment/brightbean-worker --timeout=300s

Remove-Item -Recurse -Force $overlayDir

Write-Host ""
Write-Host "=============================================="
Write-Host "  BrightBean Studio (Kubernetes) is ready"
Write-Host "=============================================="
Write-Host "  Namespace:     brightbean-studio"
Write-Host "  Workers:       $workerReplicas replicas (parallel processing)"
Write-Host ""
Write-Host "  Port-forward (run in another terminal):"
Write-Host "    kubectl -n brightbean-studio port-forward svc/brightbean-app 8000:80"
Write-Host ""
Write-Host "  Then open:"
Write-Host "    Web UI:        http://localhost:8000"
Write-Host "    Agent API:     http://localhost:8000/api/v1/"
Write-Host "    Swagger docs:  http://localhost:8000/api/v1/docs"
Write-Host ""
Write-Host "  Ingress host:    brightbean.local"
Write-Host "  Create admin:"
Write-Host "    kubectl -n brightbean-studio exec deploy/brightbean-app -- python manage.py createsuperuser"
Write-Host "=============================================="
