#!/usr/bin/env bash
# Build, test, and deploy hpapp to Kubernetes.  Usage: scripts/deploy.sh [image-tag]
set -euo pipefail
TAG="${1:-2.1.0}"
cd "$(dirname "$0")/.."

echo "==> Running tests (coverage gate >= 80%)"
python -m pytest

echo "==> Building image hpapp:${TAG}"
docker build -f docker/Dockerfile -t "hpapp:${TAG}" .

echo "==> Applying manifests"
sed "s#image: hpapp:.*#image: hpapp:${TAG}#" kubernetes/deployment.yaml | kubectl apply -f -
kubectl apply -f kubernetes/configmap.yaml -f kubernetes/service.yaml -f kubernetes/hpa.yaml
kubectl rollout status deployment/hpapp --timeout=120s
echo "==> Deployed hpapp:${TAG}"
