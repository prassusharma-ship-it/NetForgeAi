"""
Trains an IsolationForest on URL-derived features
(url_pipeline/url_features.csv, built by url_pipeline/fetch_urls.py).

Unsupervised -- flags URLs/responses whose HTTP+TLS+structural profile
looks statistically different from the rest of the batch (e.g. missing
security headers where peers have them, unusually long/hyphenated URLs,
near-expiry certs, unusual redirect chains, anomalous response times).

Run order:
    python3 url_pipeline/fetch_urls.py <url1> <url2> ...   # build the dataset
    python3 ml/train_model_from_urls.py

You'll want at least ~20-30 fetched URLs before this is meaningful --
IsolationForest needs a reasonable batch to establish what "normal" looks
like among your fetched sites.
"""

import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

sys.path.append(str(Path(__file__).resolve().parent.parent))
from ml.model import URL_FEATURES as FEATURES

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "url_pipeline" / "url_features.csv"
MODEL_PATH = ROOT / "ml" / "url_isolation_forest.joblib"
SCALER_PATH = ROOT / "ml" / "url_scaler.joblib"

CONTAMINATION = 0.1


def main():
    df = pd.read_csv(DATA_PATH)
    if df.empty:
        raise SystemExit(f"{DATA_PATH} is empty -- run fetch_urls.py first.")
    if len(df) < 10:
        print(f"Warning: only {len(df)} rows -- results will be unstable. "
              f"Fetch more URLs for a meaningful model.")

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

    preds = model.predict(X_scaled)
    df["is_anomaly"] = np.where(preds == -1, 1, 0)

    print("=== Flagged URLs ===")
    flagged = df[df["is_anomaly"] == 1]
    cols_to_show = ["url", "status_code", "response_time_ms", "has_hsts",
                     "has_csp", "cert_days_remaining"]
    print(flagged[cols_to_show].to_string(index=False) if not flagged.empty else "(none flagged)")
    print(f"\n{len(flagged)} of {len(df)} URLs flagged ({len(flagged)/len(df):.1%})")

    joblib.dump(model, MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)
    print(f"\nSaved model -> {MODEL_PATH}")
    print(f"Saved scaler -> {SCALER_PATH}")


if __name__ == "__main__":
    main()
