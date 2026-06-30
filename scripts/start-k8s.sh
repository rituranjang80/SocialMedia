#!/usr/bin/env bash
# One-click Kubernetes deploy: build image, apply manifests, port-forward UI + API
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required. Install: https://kubernetes.io/docs/tasks/tools/"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required to build the application image."
  exit 1
fi

IMAGE="${BRIGHTBEAN_IMAGE:-brightbean-studio:latest}"
WORKER_REPLICAS="${WORKER_REPLICAS:-2}"

echo "Building Docker image: $IMAGE"
docker build -t "$IMAGE" .

# Generate secrets into a temp overlay
SECRET_KEY="${SECRET_KEY:-$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))' 2>/dev/null || python -c 'import secrets; print(secrets.token_urlsafe(48))')}"
ENCRYPTION_KEY_SALT="${ENCRYPTION_KEY_SALT:-$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))' 2>/dev/null || python -c 'import secrets; print(secrets.token_urlsafe(48))')}"

OVERLAY_DIR="$(mktemp -d)"
trap 'rm -rf "$OVERLAY_DIR"' EXIT

cat > "$OVERLAY_DIR/kustomization.yaml" <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ${ROOT}/deploy/kubernetes
secretGenerator:
  - name: brightbean-studio-secrets
    behavior: replace
    literals:
      - SECRET_KEY=${SECRET_KEY}
      - ENCRYPTION_KEY_SALT=${ENCRYPTION_KEY_SALT}
patches:
  - target:
      kind: Deployment
      name: brightbean-worker
    patch: |-
      - op: replace
        path: /spec/replicas
        value: ${WORKER_REPLICAS}
images:
  - name: brightbean-studio
    newName: $(echo "$IMAGE" | cut -d: -f1)
    newTag: $(echo "$IMAGE" | cut -d: -f2)
EOF

echo "Applying Kubernetes manifests..."
kubectl apply -k "$OVERLAY_DIR"

echo "Waiting for postgres..."
kubectl -n brightbean-studio wait --for=condition=ready pod -l app.kubernetes.io/component=postgres --timeout=180s

echo "Running database migrations..."
kubectl -n brightbean-studio delete job brightbean-migrate --ignore-not-found
kubectl -n brightbean-studio apply -f "$ROOT/deploy/kubernetes/migrate-job.yaml"
kubectl -n brightbean-studio wait --for=condition=complete job/brightbean-migrate --timeout=300s

echo "Waiting for app deployment..."
kubectl -n brightbean-studio rollout status deployment/brightbean-app --timeout=300s
kubectl -n brightbean-studio rollout status deployment/brightbean-worker --timeout=300s

echo ""
echo "=============================================="
echo "  BrightBean Studio (Kubernetes) is ready"
echo "=============================================="
echo "  Namespace:     brightbean-studio"
echo "  Workers:       ${WORKER_REPLICAS} replicas (parallel processing)"
echo ""
echo "  Port-forward (run in another terminal):"
echo "    kubectl -n brightbean-studio port-forward svc/brightbean-app 8000:80"
echo ""
echo "  Then open:"
echo "    Web UI:        http://localhost:8000"
echo "    Agent API:     http://localhost:8000/api/v1/"
echo "    Swagger docs:  http://localhost:8000/api/v1/docs"
echo ""
echo "  Ingress host:    brightbean.local (add to /etc/hosts if using ingress)"
echo "  Create admin:"
echo "    kubectl -n brightbean-studio exec deploy/brightbean-app -- python manage.py createsuperuser"
echo "=============================================="
