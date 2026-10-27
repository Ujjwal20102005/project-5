# Deployment Instructions

## Local
```bash
pip install -r requirements.txt
PYTHONPATH=src python -m hpapp.main          # http://localhost:8080
python scripts/load_test.py 127.0.0.1 8080 1000 100
```

## Docker / Compose (app + Prometheus + Grafana)
```bash
docker compose -f docker/docker-compose.yml up --build
# app :8080   prometheus :9090   grafana :3000 (import monitoring/grafana/dashboard.json)
```

## Kubernetes
```bash
docker build -f docker/Dockerfile -t hpapp:2.1.0 .
scripts/deploy.sh 2.1.0       # runs tests, builds, applies manifests, waits for rollout
```
Manifests: `configmap.yaml`, `deployment.yaml` (3 replicas, rolling update with zero unavailable,
probes, resource limits, non-root), `service.yaml`, `hpa.yaml` (3-20 pods at 70% CPU).
Pods handle `SIGTERM` gracefully (stop accepting connections, close DB).

## Configuration
All settings are `HPAPP_*` environment variables (`src/hpapp/config.py`). See `kubernetes/configmap.yaml`.
