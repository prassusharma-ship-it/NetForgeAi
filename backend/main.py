"""
Backend service: ingests traffic flows, scores them with the trained model,
stores results, and pushes live updates to the dashboard over WebSocket.

Run:
    pip install fastapi uvicorn[standard] joblib scikit-learn pandas numpy
    uvicorn backend.main:app --reload --port 8000

Endpoints:
    POST /ingest        -> submit one traffic flow, get back a verdict
    POST /analyze-url    -> give a URL, get back fetched features + a verdict
    GET  /alerts           -> list recent flagged alerts
    GET  /stats             -> summary counters for the dashboard
    WS   /ws/live             -> live stream of every scored flow + alerts

Storage is in-memory for the prototype (a Python list). Swap in
PostgreSQL/TimescaleDB for anything beyond a demo -- the insert points
are marked below with TODO comments so that swap is a small, contained
change.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))  # so `ml` imports work

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ml.model import AnomalyScorer, TrendForecaster, URL_FEATURES, now_iso

sys.path.append(str(Path(__file__).resolve().parent.parent / "url_pipeline"))
from url_feature_extractor import extract_features as extract_url_features

app = FastAPI(title="AI Network Attack Forecasting - Prototype")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this before anything resembling production
    allow_methods=["*"],
    allow_headers=["*"],
)

MODEL_DIR = Path(__file__).resolve().parent.parent / "ml"
scorer = AnomalyScorer(
    model_path=str(MODEL_DIR / "isolation_forest.joblib"),
    scaler_path=str(MODEL_DIR / "scaler.joblib"),
)
forecaster = TrendForecaster(window_size=50, z_threshold=2.0)

# URL-based scorer is optional -- only loads if you've run
# ml/train_model_from_urls.py. /analyze-url returns a clear error until then.
try:
    url_scorer = AnomalyScorer(
        model_path=str(MODEL_DIR / "url_isolation_forest.joblib"),
        scaler_path=str(MODEL_DIR / "url_scaler.joblib"),
        features=URL_FEATURES,
    )
except FileNotFoundError:
    url_scorer = None

# --- in-memory storage (TODO: replace with PostgreSQL/TimescaleDB) ---
ALL_EVENTS = []
ALERTS = []
STATS = {"total_flows": 0, "total_alerts": 0}


class TrafficFlow(BaseModel):
    flow_id: int
    src_ip: str | None = "unknown"
    dst_ip: str | None = "unknown"
    duration_ms: float
    packet_rate: float
    byte_rate: float
    unique_dst_ports: float
    syn_flag_ratio: float
    avg_packet_size: float
    protocol: float


class UrlRequest(BaseModel):
    url: str


# --- WebSocket connection manager ---
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


@app.post("/ingest")
async def ingest_flow(flow: TrafficFlow):
    flow_dict = flow.model_dump()
    verdict = scorer.score(flow_dict)
    trend = forecaster.update(verdict["is_anomaly"])

    event = {
        "timestamp": now_iso(),
        **flow_dict,
        **verdict,
        **trend,
    }

    ALL_EVENTS.append(event)          # TODO: INSERT INTO traffic_events
    STATS["total_flows"] += 1

    if verdict["is_anomaly"]:
        ALERTS.append(event)          # TODO: INSERT INTO alerts
        STATS["total_alerts"] += 1

    await manager.broadcast({"type": "flow_scored", "data": event})
    return {"verdict": verdict, "trend": trend}


@app.post("/analyze-url")
async def analyze_url(req: UrlRequest):
    """
    Give it a URL, it fetches the page (HTTP + TLS metadata only -- same
    data a browser sees), extracts feature columns, and scores it.
    Requires ml/train_model_from_urls.py to have been run at least once.
    """
    if url_scorer is None:
        return {
            "error": (
                "URL model not trained yet. Run: "
                "python3 url_pipeline/fetch_urls.py <a few urls>  then  "
                "python3 ml/train_model_from_urls.py"
            )
        }

    features = extract_url_features(req.url)
    if features["fetch_error"]:
        return {"url": req.url, "fetch_error": features["fetch_error"], "verdict": None}

    verdict = url_scorer.score(features)

    event = {
        "timestamp": now_iso(),
        "type": "url_analysis",
        **features,
        **verdict,
    }
    await manager.broadcast({"type": "url_scored", "data": event})

    return {
        "url": req.url,
        "final_url": features["final_url"],
        "status_code": features["status_code"],
        "response_time_ms": features["response_time_ms"],
        "has_hsts": bool(features["has_hsts"]),
        "has_csp": bool(features["has_csp"]),
        "has_xframe": bool(features["has_xframe"]),
        "cert_days_remaining": features["cert_days_remaining"],
        "verdict": verdict,
    }


@app.get("/alerts")
async def get_alerts(limit: int = 50):
    return {"alerts": ALERTS[-limit:][::-1]}


@app.get("/stats")
async def get_stats():
    top_ips: dict[str, int] = {}
    for a in ALERTS:
        top_ips[a["src_ip"]] = top_ips.get(a["src_ip"], 0) + 1
    top_offenders = sorted(top_ips.items(), key=lambda x: -x[1])[:5]

    return {
        **STATS,
        "attack_rate": round(STATS["total_alerts"] / max(STATS["total_flows"], 1), 3),
        "top_offenders": [{"ip": ip, "count": c} for ip, c in top_offenders],
    }


@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive; client doesn't need to send real data
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/")
async def root():
    return {"status": "ok", "service": "network-attack-forecasting-backend"}
