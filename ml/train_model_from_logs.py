"""
Trains an IsolationForest on SSH-auth-log-derived features
(log_pipeline/log_features.csv, produced by log_pipeline/log_parser.py).

Unlike train_model.py, this is FULLY UNSUPERVISED -- there's no 'label'
column, because real captured logs don't come with ground truth. That's
the whole point of anomaly detection here: it flags source IPs whose
behavior (attempt rate, fail ratio, burstiness) looks statistically
different from the bulk of normal connections, without needing you to
have pre-labeled which IPs were attackers.

Run order:
    python3 log_pipeline/generate_sample_authlog.py   # or ssh_fetcher.py for real data
    python3 log_pipeline/log_parser.py
    python3 ml/train_model_from_logs.py
"""

import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

sys.path.append(str(Path(__file__).resolve().parent.parent))
from ml.model import LOG_FEATURES as FEATURES

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "log_pipeline" / "log_features.csv"
MODEL_PATH = ROOT / "ml" / "log_isolation_forest.joblib"
SCALER_PATH = ROOT / "ml" / "log_scaler.joblib"

# Expected fraction of windows that are actually malicious -- tune this
# once you've eyeballed a batch of real logs from your own VPS.
CONTAMINATION = 0.1


def main():
    df = pd.read_csv(DATA_PATH)
    if df.empty:
        raise SystemExit(f"{DATA_PATH} is empty -- run log_parser.py first.")

    X = df[FEATURES].values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = IsolationForest(
        n_estimators=200,
        contamination=CONTAMINATION,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_scaled)

    preds = model.predict(X_scaled)  # 1 normal, -1 anomaly
    df["is_anomaly"] = np.where(preds == -1, 1, 0)

    print("=== Flagged windows (top by src_ip) ===")
    flagged = df[df["is_anomaly"] == 1]
    print(flagged[["window_start", "src_ip", "attempt_count", "fail_ratio",
                    "max_attempts_per_second"]].to_string(index=False))
    print(f"\n{len(flagged)} of {len(df)} windows flagged as anomalous "
          f"({len(flagged)/len(df):.1%})")

    joblib.dump(model, MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)
    print(f"\nSaved model -> {MODEL_PATH}")
    print(f"Saved scaler -> {SCALER_PATH}")


if __name__ == "__main__":
    main()
