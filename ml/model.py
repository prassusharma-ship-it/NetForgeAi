"""
Scoring layer used by the FastAPI backend.

Two pieces, matching the "forecasting" framing of the problem statement:

1. AnomalyScorer  -- per-flow (or per-log-window) anomaly detection using
   a trained IsolationForest. Generalized to accept any ordered list of
   feature names, so the SAME class scores either netflow-style rows
   (data/traffic.csv) or SSH-log-derived rows (log_pipeline/log_features.csv).

2. TrendForecaster -- rolling-window forecasting (is attack VOLUME trending
   up, i.e. should we expect a spike soon?) using a simple EWMA + z-score
   on the rate of anomalies over time. Intentionally lightweight (no LSTM)
   so it is dependable in a live demo -- swap in an LSTM/Prophet model
   later without changing the backend's interface.
"""

from collections import deque
from datetime import datetime, timezone

import joblib
import numpy as np

# Default feature set for the netflow-based model (data/traffic.csv).
NETFLOW_FEATURES = [
    "duration_ms", "packet_rate", "byte_rate", "unique_dst_ports",
    "syn_flag_ratio", "avg_packet_size", "protocol",
]

# Feature set for the SSH-auth-log-based model (log_pipeline/log_features.csv).
LOG_FEATURES = [
    "attempt_count", "failed_count", "success_count", "fail_ratio",
    "unique_usernames", "invalid_user_ratio",
    "avg_seconds_between_attempts", "max_attempts_per_second",
]

# Feature set for the URL-based model (url_pipeline/url_features.csv).
# Must match url_pipeline/url_feature_extractor.py's FEATURE_COLUMNS exactly.
URL_FEATURES = [
    "url_length", "num_dots", "num_hyphens", "num_digits", "num_subdomains",
    "is_ip_host", "has_https", "num_redirects", "response_time_ms",
    "status_code", "content_length", "has_hsts", "has_csp", "has_xframe",
    "cert_days_remaining",
]


class AnomalyScorer:
    def __init__(self, model_path: str, scaler_path: str, features: list[str] = None):
        self.model = joblib.load(model_path)
        self.scaler = joblib.load(scaler_path)
        self.features = features or NETFLOW_FEATURES

    def score(self, row: dict) -> dict:
        """Returns anomaly verdict + a 0-1 severity score for one row."""
        x = np.array([[row[f] for f in self.features]], dtype=float)
        x_scaled = self.scaler.transform(x)

        raw_pred = self.model.predict(x_scaled)[0]        # 1 normal, -1 anomaly
        raw_score = self.model.decision_function(x_scaled)[0]  # higher = more normal

        is_anomaly = bool(raw_pred == -1)
        severity = float(np.clip(0.5 - raw_score, 0, 1))

        return {
            "is_anomaly": is_anomaly,
            "severity": round(severity, 3),
        }


class TrendForecaster:
    """
    Tracks the recent rate of anomalies in a sliding window and flags
    when it's trending significantly above baseline -- a proxy for
    "an attack wave may be building."
    """

    def __init__(self, window_size: int = 50, z_threshold: float = 2.0):
        self.window = deque(maxlen=window_size)
        self.z_threshold = z_threshold

    def update(self, is_anomaly: bool) -> dict:
        self.window.append(1 if is_anomaly else 0)

        if len(self.window) < 10:
            return {"risk_trend": "insufficient_data", "z_score": 0.0}

        arr = np.array(self.window)
        mean, std = arr.mean(), arr.std() or 1e-6
        current_rate = arr[-10:].mean()
        z = (current_rate - mean) / std

        if z > self.z_threshold:
            trend = "rising"
        elif z < -self.z_threshold:
            trend = "falling"
        else:
            trend = "stable"

        return {"risk_trend": trend, "z_score": round(float(z), 3)}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
