"""
Trains the core anomaly-detection model on flow-level traffic features.

Swap data/traffic.csv for real CICIDS2017 data when you have it -- the
feature columns here are deliberately a subset of what CICIDS2017 provides
so this script keeps working with either.

For the SSH-auth-log-derived dataset instead, use train_model_from_logs.py.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import joblib
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from ml.model import NETFLOW_FEATURES as FEATURES

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "traffic.csv"
MODEL_PATH = ROOT / "ml" / "isolation_forest.joblib"
SCALER_PATH = ROOT / "ml" / "scaler.joblib"


def main():
    df = pd.read_csv(DATA_PATH)
    X = df[FEATURES].values
    y = df["label"].values  # only used for evaluation below

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    contamination = max(y_train.mean(), 0.01)
    model = IsolationForest(
        n_estimators=200,
        contamination=contamination,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train_scaled)

    raw_preds = model.predict(X_test_scaled)
    y_pred = np.where(raw_preds == -1, 1, 0)

    print("=== Evaluation on held-out synthetic data ===")
    print(classification_report(y_test, y_pred, target_names=["benign", "attack"]))
    print("Confusion matrix [rows=true, cols=pred]:")
    print(confusion_matrix(y_test, y_pred))

    joblib.dump(model, MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)
    print(f"\nSaved model -> {MODEL_PATH}")
    print(f"Saved scaler -> {SCALER_PATH}")


if __name__ == "__main__":
    main()
