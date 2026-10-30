# NetForge — Deployment Guide

This document covers running the prototype locally, then deploying to production-grade infrastructure.

---

## 🖥️ Local Development (Already Working)

### Prerequisites
- Python 3.10+
- pip
- Git

### Quick Start (3 terminals)

```bash
# Terminal 1: Start backend API
python run_demo.py
# OR manually:
# python data/generate_synthetic_traffic.py
# python ml/train_model.py
# uvicorn backend.main:app --reload --port 8000

# Terminal 2: Replay synthetic traffic
python simulator/replay.py

# Terminal 3: Open dashboard
open dashboard/index.html   # macOS
# xdg-open dashboard/index.html  # Linux
```

### Verify It's Working
```bash
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/stats
curl -X POST http://127.0.0.1:8000/analyze-url -H "Content-Type: application/json" -d '{"url": "https://example.com"}'
```

---

## 📦 Pipeline B: SSH Logs (Real Server)

### Option 1: Offline Test (No Server Needed)
```bash
python log_pipeline/generate_sample_authlog.py
python log_pipeline/log_parser.py
python ml/train_model_from_logs.py
```

### Option 2: Real VPS/Server
```bash
# 1. Configure connection
cp log_pipeline/config.example.py log_pipeline/config.py
# Edit config.py with your VPS details (host, user, key_path)

# 2. Fetch logs via SSH
python log_pipeline/ssh_fetcher.py --host YOUR_VPS_IP --user root --key-path ~/.ssh/id_rsa

# 3. Parse → features
python log_pipeline/log_parser.py

# 4. Train model
python ml/train_model_from_logs.py

# 5. (Future) Wire into backend — see README "Connecting Pipeline B"
```

---

## 🌐 Pipeline C: URL Analysis

### Build Training Dataset
```bash
# Fetch 15-20 diverse URLs (mix of normal sites)
python url_pipeline/fetch_urls.py https://example.com https://github.com https://google.com ...

# Or from file (one URL per line)
python url_pipeline/fetch_urls.py --file url_pipeline/watchlist.txt
```

### Train URL Model
```bash
python ml/train_model_from_urls.py
```

### Test Live
```bash
curl -X POST http://127.0.0.1:8000/analyze-url \
  -H "Content-Type: application/json" \
  -d '{"url": "https://suspicious-site.xyz"}'
```

---

## 🐳 Docker Deployment (Recommended for Production)

### Dockerfile
```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app

# System deps for paramiko, cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-train models at build time (so container starts fast)
RUN python data/generate_synthetic_traffic.py && \
    python ml/train_model.py && \
    python log_pipeline/generate_sample_authlog.py && \
    python log_pipeline/log_parser.py && \
    python ml/train_model_from_logs.py

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

### Build & Run
```bash
docker build -t netforge .
docker run -d -p 8000:8000 --name netforge-api netforge

# Verify
curl http://localhost:8000/health
```

### Docker Compose (Full Stack)
```yaml
# docker-compose.yml
version: "3.8"

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/netforge
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: "1"
          memory: 1G

  db:
    image: timescale/timescaledb:latest-pg16
    environment:
      POSTGRES_DB: netforge
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  dashboard:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./dashboard:/usr/share/nginx/html:ro
    depends_on:
      - api

volumes:
  pgdata:
```

```bash
docker compose up -d --build
# Dashboard at http://localhost
# API at http://localhost:8000
```

---

## ☸️ Kubernetes Deployment

### Namespace & Config
```yaml
# k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: netforge
```

### ConfigMap (Non-secret config)
```yaml
# k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: netforge-config
  namespace: netforge
data:
  DATABASE_URL: "postgresql://postgres:postgres@postgres:5432/netforge"
  REDIS_URL: "redis://redis:6379/0"
  LOG_LEVEL: "INFO"
  WINDOW_SECONDS: "60"
```

### Secret (Sensitive values)
```yaml
# k8s/secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: netforge-secrets
  namespace: netforge
type: Opaque
stringData:
  SSH_KEY: "<base64-encoded-private-key>"
  API_KEY: "your-secure-api-key"
```

### Deployment
```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: netforge-api
  namespace: netforge
spec:
  replicas: 3
  selector:
    matchLabels:
      app: netforge-api
  template:
    metadata:
      labels:
        app: netforge-api
    spec:
      containers:
        - name: api
          image: your-registry/netforge:latest
          ports:
            - containerPort: 8000
          envFrom:
            - configMapRef:
                name: netforge-config
            - secretRef:
                name: netforge-secrets
          resources:
            requests:
              memory: "512Mi"
              cpu: "250m"
            limits:
              memory: "1Gi"
              cpu: "1000m"
          livenessProbe:
            httpGet:
              path: /
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /stats
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 10
```

### Service & Ingress
```yaml
# k8s/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: netforge-api
  namespace: netforge
spec:
  selector:
    app: netforge-api
  ports:
    - port: 80
      targetPort: 8000
  type: ClusterIP
---
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: netforge-ingress
  namespace: netforge
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
spec:
  tls:
    - hosts:
        - netforge.yourdomain.com
      secretName: netforge-tls
  rules:
    - host: netforge.yourdomain.com
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: netforge-api
                port:
                  number: 80
          - path: /
            pathType: Prefix
            backend:
              service:
                name: netforge-dashboard
                port:
                  number: 80
```

### Apply
```bash
kubectl apply -f k8s/
kubectl -n netforge get pods -w
```

---

## 🔧 Production Hardening Checklist

### Security
- [ ] Replace `allow_origins=["*"]` in `backend/main.py` with your dashboard domain
- [ ] Add API key authentication (middleware) to `/ingest`, `/analyze-url`
- [ ] Use TLS everywhere (cert-manager + Let's Encrypt on K8s)
- [ ] Store SSH keys in Vault/SealedSecrets, not plain Kubernetes Secrets
- [ ] Rate-limit `/analyze-url` (prevent abuse)
- [ ] Validate/allowlist URLs for `/analyze-url` (SSRF protection)

### Observability
- [ ] Add structured logging (JSON) → Loki/ELK
- [ ] Add Prometheus metrics (`/metrics` endpoint)
- [ ] Add distributed tracing (OpenTelemetry → Jaeger/Tempo)
- [ ] Alert on: high anomaly rate, model drift, fetch failures

### Data Persistence (Replace In-Memory)
```python
# backend/main.py — TODO markers already in code
# Replace ALL_EVENTS, ALERTS, STATS with:

# PostgreSQL (TimescaleDB for time-series)
import asyncpg
pool = await asyncpg.create_pool(DATABASE_URL)

async def insert_event(event):
    await pool.execute("""
        INSERT INTO traffic_events (timestamp, flow_id, src_ip, dst_ip, 
            duration_ms, packet_rate, byte_rate, unique_dst_ports,
            syn_flag_ratio, avg_packet_size, protocol,
            is_anomaly, severity, risk_trend, z_score)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
    """, *event.values())

# Redis for real-time stats
import redis.asyncio as redis
r = redis.from_url(REDIS_URL)
await r.incr("total_flows")
await r.zincrby("top_offenders", 1, event["src_ip"])
```

### Model Management
- [ ] Version models (MLflow or DVC)
- [ ] A/B test new models before full rollout
- [ ] Monitor feature drift (compare live feature distributions to training)
- [ ] Retrain on schedule (cron job → `train_model.py` → push new artifact)

### Scaling
- [ ] Horizontal pod autoscaler (HPA) on CPU + custom metric (requests/sec)
- [ ] WebSocket connection scaling (use Redis pub/sub for multi-pod broadcast)
- [ ] Separate ingest workers (Celery/RQ) from API pods
- [ ] Batch ingest endpoint (`POST /ingest-batch`) for high-throughput sources

---

## 📊 Monitoring Dashboard (Grafana)

### Key Dashboards to Build
1. **Traffic Overview** — flows/sec, alert rate, top IPs
2. **Model Health** — anomaly score distribution, feature drift
3. **Pipeline B (SSH)** — auth attempts/min, unique IPs, fail ratio
4. **Pipeline C (URL)** — URLs analyzed, fetch latency, verdict breakdown
5. **System** — API latency, error rate, pod count, DB connections

### Example Prometheus Queries
```promql
# Anomaly rate over 5m
rate(netforge_anomalies_total[5m])

# P95 API latency
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Top offending IPs (last hour)
topk(10, sum by (src_ip) (rate(netforge_alerts_total[1h])))
```

---

## 🚀 CI/CD Pipeline (GitHub Actions)

```yaml
# .github/workflows/ci.yml
name: CI/CD

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: python -m pytest tests/ -v
      - run: python data/generate_synthetic_traffic.py
      - run: python ml/train_model.py
      - run: python log_pipeline/generate_sample_authlog.py && python log_pipeline/log_parser.py && python ml/train_model_from_logs.py

  docker:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/build-push-action@v5
        with:
          push: true
          tags: ghcr.io/${{ github.repository }}/netforge:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy-staging:
    needs: docker
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: azure/k8s-set-context@v1
        with:
          kubeconfig: ${{ secrets.KUBECONFIG_STAGING }}
      - run: |
          kubectl set image deployment/netforge-api \
            api=ghcr.io/${{ github.repository }}/netforge:${{ github.sha }} \
            -n netforge-staging
```

---

## 📁 Project Structure for Production

```
netforge/
├── backend/                 # FastAPI service
│   ├── main.py
│   ├── auth.py             # API key middleware
│   ├── database.py         # PostgreSQL/TimescaleDB
│   ├── redis_client.py     # Redis for real-time
│   └── websocket_manager.py
├── ml/                     # Model training & scoring
│   ├── model.py
│   ├── train_model.py
│   ├── train_model_from_logs.py
│   ├── train_model_from_urls.py
│   └── registry.py         # MLflow/DVC integration
├── log_pipeline/           # SSH log ingestion
│   ├── ssh_fetcher.py
│   ├── log_parser.py
│   ├── config.py           # Server credentials (gitignored)
│   └── scheduler.py        # Cron-like periodic fetch
├── url_pipeline/           # URL analysis
│   ├── fetch_urls.py
│   ├── url_feature_extractor.py
│   └── watchlist.txt
├── simulator/              # Demo traffic generator
│   └── replay.py
├── data/                   # Synthetic data gen
│   └── generate_synthetic_traffic.py
├── dashboard/              # Static HTML/JS
│   └── index.html
├── k8s/                    # Kubernetes manifests
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   └── ingress.yaml
├── tests/                  # Unit + integration tests
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── run_demo.py
└── DEPLOYMENT.md           # This file
```

---

## 🎯 Next Steps for Your Hackathon Demo

1. **Run locally** — `python run_demo.py` + `python simulator/replay.py` + open dashboard
2. **Add SSH log demo** — Run Pipeline B commands, show `log_features.csv` and flagged IPs
3. **Add URL demo** — Type a suspicious URL in dashboard "Check a URL" box
4. **Prepare slides** — Architecture diagram, data flow, ML approach (Isolation Forest)
5. **Optional: Dockerize** — `docker build -t netforge . && docker run -p 8000:8000 netforge`

---

## 🆘 Troubleshooting

| Issue | Fix |
|-------|-----|
| `address already in use` | `lsof -i :8000` → `kill -9 <PID>` |
| Model not found | Run training scripts first (`train_model.py`, etc.) |
| Dashboard shows "disconnected" | Backend not running or wrong WS URL in `index.html` |
| URL fetch fails | Check network, some sites block automated requests |
| SSH fetch fails | Verify key permissions (`chmod 600 ~/.ssh/id_rsa`), test `ssh user@host` manually |
| `InconsistentVersionWarning` | Re-train models with current scikit-learn version |

---

## 📞 Support

- Check `backend/main.py` TODO comments for PostgreSQL/TimescaleDB integration points
- `ml/model.py` — `AnomalyScorer` and `TrendForecaster` are pipeline-agnostic
- All three pipelines share the same scoring interface — easy to extend