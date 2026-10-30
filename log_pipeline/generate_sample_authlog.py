"""
Generates a synthetic /var/log/auth.log-style text file so you can build
and test the parser end-to-end WITHOUT a live VPS/SSH connection yet.

Once ssh_fetcher.py is pulling real logs from your server, point
log_parser.py at that output instead -- the format matches real
OpenSSH sshd log lines, so the parser works on both.

Real auth.log lines look like:
    Sep 12 14:23:01 vps-server sshd[14231]: Failed password for invalid user admin from 45.33.12.9 port 51422 ssh2
    Sep 12 14:23:03 vps-server sshd[14231]: Failed password for root from 45.33.12.9 port 51430 ssh2
    Sep 12 14:23:10 vps-server sshd[14290]: Accepted password for deploy from 10.0.0.5 port 22110 ssh2
"""

import random
from datetime import datetime, timedelta
from pathlib import Path

RNG = random.Random(42)
OUT_PATH = Path(__file__).resolve().parent / "sample_auth.log"

NORMAL_USERS = ["deploy", "ubuntu", "admin_ops", "ci_runner"]
NORMAL_IPS = ["10.0.0.5", "10.0.0.9", "192.168.1.20"]

ATTACK_USERS = ["root", "admin", "test", "oracle", "postgres", "pi", "user", "guest"]
ATTACK_IPS = ["45.33.12.9", "103.21.244.5", "185.220.101.4"]

HOST = "vps-server"


def fmt(ts, msg):
    return f"{ts.strftime('%b %d %H:%M:%S')} {HOST} sshd[{RNG.randint(1000,30000)}]: {msg}"


def normal_traffic(start, n):
    lines = []
    t = start
    for _ in range(n):
        ip = RNG.choice(NORMAL_IPS)
        user = RNG.choice(NORMAL_USERS)
        port = RNG.randint(40000, 60000)
        lines.append(fmt(t, f"Accepted password for {user} from {ip} port {port} ssh2"))
        t += timedelta(seconds=RNG.randint(30, 400))
    return lines, t


def brute_force_burst(start, n):
    """Rapid-fire failed logins from one attacker IP -- the pattern we want flagged."""
    lines = []
    ip = RNG.choice(ATTACK_IPS)
    t = start
    for _ in range(n):
        user = RNG.choice(ATTACK_USERS)
        port = RNG.randint(40000, 60000)
        msg = f"Failed password for invalid user {user} from {ip} port {port} ssh2"
        lines.append(fmt(t, msg))
        t += timedelta(seconds=RNG.uniform(0.5, 3))
    return lines, t


def main():
    start = datetime(2026, 9, 12, 9, 0, 0)
    all_lines = []

    t = start
    for _ in range(6):
        lines, t = normal_traffic(t, RNG.randint(5, 12))
        all_lines += lines
        if RNG.random() < 0.6:
            lines, t = brute_force_burst(t, RNG.randint(15, 60))
            all_lines += lines

    with open(OUT_PATH, "w") as f:
        f.write("\n".join(all_lines) + "\n")

    print(f"Wrote {len(all_lines)} synthetic auth.log lines to {OUT_PATH}")


if __name__ == "__main__":
    main()
