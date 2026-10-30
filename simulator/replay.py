"""
Replays traffic.csv into the backend's /ingest endpoint at a controlled
rate, so the dashboard has something "live" to show during a demo without
needing an actual live network capture.

Run (after the backend is up):
    pip install requests pandas
    python3 simulator/replay.py
"""

import time
import random
from pathlib import Path

import pandas as pd
import requests

BACKEND_URL = "http://localhost:8000/ingest"
DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "traffic.csv"
DELAY_SECONDS = 0.15
BURST_EVERY = 40


def fake_ip():
    return f"10.0.{random.randint(0, 5)}.{random.randint(1, 254)}"


def main():
    df = pd.read_csv(DATA_PATH)
    print(f"Replaying {len(df)} flows to {BACKEND_URL}")

    for i, row in df.iterrows():
        payload = row.drop(labels=["label"]).to_dict()
        payload["src_ip"] = fake_ip()
        payload["dst_ip"] = "10.0.0.1"

        try:
            resp = requests.post(BACKEND_URL, json=payload, timeout=2)
            resp.raise_for_status()
            verdict = resp.json()["verdict"]
            tag = "ALERT" if verdict["is_anomaly"] else "ok"
            print(f"[{i}] flow_id={payload['flow_id']} -> {tag} "
                  f"(severity={verdict['severity']})")
        except requests.RequestException as e:
            print(f"Failed to send flow {payload.get('flow_id')}: {e}")

        time.sleep(DELAY_SECONDS)

        if i % BURST_EVERY == 0 and i > 0:
            time.sleep(0.5)


if __name__ == "__main__":
    main()
