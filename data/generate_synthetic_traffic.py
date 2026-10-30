"""
Generates synthetic network-flow data shaped like CICIDS2017 features.

Why synthetic data: for the real prototype, download CICIDS2017 from
https://www.unb.ca/cic/datasets/ids-2017.html and point train_model.py at
the CSV instead. This generator exists so you can build/test the entire
pipeline (model -> backend -> dashboard) offline, right now, without
waiting on a multi-GB download. Swap it out once you have the real data.

Output: data/traffic.csv with flow-level features + a 'label' column
(0 = benign, 1 = attack). Attack rows simulate three common patterns:
DDoS (high packet rate, short duration), port scan (many unique
destination ports, tiny packets), and brute force (repeated short
connections to one port).
"""

from pathlib import Path

import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)
N_BENIGN = 8000
N_DDOS = 700
N_PORTSCAN = 700
N_BRUTEFORCE = 600


def make_benign(n):
    return pd.DataFrame({
        "duration_ms": RNG.gamma(shape=3, scale=200, size=n),
        "packet_rate": RNG.normal(15, 5, n).clip(0.1),
        "byte_rate": RNG.normal(2000, 800, n).clip(50),
        "unique_dst_ports": RNG.integers(1, 4, n),
        "syn_flag_ratio": RNG.uniform(0.05, 0.3, n),
        "avg_packet_size": RNG.normal(500, 150, n).clip(40),
        "protocol": RNG.choice([6, 17], size=n, p=[0.8, 0.2]),  # TCP / UDP
        "label": 0,
    })


def make_ddos(n):
    return pd.DataFrame({
        "duration_ms": RNG.gamma(shape=1, scale=20, size=n),
        "packet_rate": RNG.normal(900, 200, n).clip(100),
        "byte_rate": RNG.normal(50000, 15000, n).clip(5000),
        "unique_dst_ports": RNG.integers(1, 3, n),
        "syn_flag_ratio": RNG.uniform(0.7, 1.0, n),
        "avg_packet_size": RNG.normal(64, 10, n).clip(40),
        "protocol": RNG.choice([6, 17], size=n, p=[0.6, 0.4]),
        "label": 1,
    })


def make_portscan(n):
    return pd.DataFrame({
        "duration_ms": RNG.gamma(shape=1, scale=5, size=n),
        "packet_rate": RNG.normal(50, 15, n).clip(5),
        "byte_rate": RNG.normal(300, 100, n).clip(20),
        "unique_dst_ports": RNG.integers(30, 500, n),
        "syn_flag_ratio": RNG.uniform(0.8, 1.0, n),
        "avg_packet_size": RNG.normal(48, 8, n).clip(40),
        "protocol": 6,
        "label": 1,
    })


def make_bruteforce(n):
    return pd.DataFrame({
        "duration_ms": RNG.gamma(shape=2, scale=50, size=n),
        "packet_rate": RNG.normal(30, 10, n).clip(2),
        "byte_rate": RNG.normal(1200, 400, n).clip(100),
        "unique_dst_ports": 1,
        "syn_flag_ratio": RNG.uniform(0.4, 0.7, n),
        "avg_packet_size": RNG.normal(200, 50, n).clip(40),
        "protocol": 6,
        "label": 1,
    })


def main():
    df = pd.concat(
        [make_benign(N_BENIGN), make_ddos(N_DDOS),
         make_portscan(N_PORTSCAN), make_bruteforce(N_BRUTEFORCE)],
        ignore_index=True,
    )
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)  # shuffle
    df.insert(0, "flow_id", range(1, len(df) + 1))
    out_path = Path(__file__).resolve().parent / "traffic.csv"
    df.to_csv(out_path, index=False)
    print(f"Wrote {len(df)} rows to {out_path}")
    print(df["label"].value_counts())


if __name__ == "__main__":
    main()
