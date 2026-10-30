"""
Parses raw OpenSSH auth.log-style text (from ssh_fetcher.py, or the
synthetic sample from generate_sample_authlog.py) into structured,
per-source-IP, per-time-window FEATURE ROWS ready for model training.

This is the "extract important feature columns from raw log text" step.

Recognizes the standard sshd log line types:
    Failed password for invalid user <user> from <ip> port <port> ssh2
    Failed password for <user> from <ip> port <port> ssh2
    Accepted password for <user> from <ip> port <port> ssh2
    Invalid user <user> from <ip> port <port>

Output columns (one row per source IP per WINDOW_SECONDS window):
    window_start        -- start of the time bucket (ISO timestamp)
    src_ip               -- source IP of the connection attempts
    attempt_count         -- total auth attempts (accepted + failed) in window
    failed_count           -- failed attempts in window
    success_count            -- accepted logins in window
    fail_ratio                 -- failed_count / attempt_count
    unique_usernames            -- distinct usernames tried
    invalid_user_ratio            -- fraction of attempts against nonexistent users
    avg_seconds_between_attempts   -- mean gap between consecutive attempts from this IP
    max_attempts_per_second          -- burstiness signal (brute force = high)

These feed straight into ml/train_model_from_logs.py (IsolationForest,
unsupervised -- no labels needed, which matches reality: you rarely have
ground truth for real captured logs).
"""

import argparse
import glob
import os
import re
from collections import defaultdict
from datetime import datetime

WINDOW_SECONDS = 60
CURRENT_YEAR = datetime.now().year  # syslog lines have no year, assume current

LINE_RE = re.compile(
    r"^(?P<month_day_time>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<host>\S+)\s+sshd\[\d+\]:\s+(?P<message>.*)$"
)

FAILED_RE = re.compile(
    r"Failed password for (invalid user )?(?P<user>\S+) from (?P<ip>[\d.]+) port (?P<port>\d+)"
)
ACCEPTED_RE = re.compile(
    r"Accepted password for (?P<user>\S+) from (?P<ip>[\d.]+) port (?P<port>\d+)"
)
INVALID_USER_RE = re.compile(
    r"^Invalid user (?P<user>\S+) from (?P<ip>[\d.]+)"
)


def parse_timestamp(month_day_time: str) -> datetime:
    return datetime.strptime(f"{CURRENT_YEAR} {month_day_time}", "%Y %b %d %H:%M:%S")


def parse_log_file(path: str):
    """Yields (timestamp, ip, user, event_type) tuples. event_type in {failed, accepted, invalid}."""
    with open(path, "r", errors="replace") as f:
        for line in f:
            line = line.strip()
            m = LINE_RE.match(line)
            if not m:
                continue
            ts = parse_timestamp(m.group("month_day_time"))
            msg = m.group("message")

            fm = FAILED_RE.search(msg)
            if fm:
                yield ts, fm.group("ip"), fm.group("user"), "failed"
                continue

            am = ACCEPTED_RE.search(msg)
            if am:
                yield ts, am.group("ip"), am.group("user"), "accepted"
                continue

            im = INVALID_USER_RE.search(msg)
            if im:
                yield ts, im.group("ip"), im.group("user"), "invalid"
                continue


def bucket_start(ts: datetime, window_seconds: int) -> datetime:
    epoch_seconds = int(ts.timestamp())
    bucket_epoch = epoch_seconds - (epoch_seconds % window_seconds)
    return datetime.fromtimestamp(bucket_epoch)


def extract_features(events, window_seconds: int = WINDOW_SECONDS):
    """
    events: iterable of (timestamp, ip, user, event_type)
    Returns list of dict rows, one per (window, src_ip).
    """
    groups = defaultdict(list)
    for ts, ip, user, event_type in events:
        key = (bucket_start(ts, window_seconds), ip)
        groups[key].append((ts, user, event_type))

    rows = []
    for (window, ip), evs in groups.items():
        evs.sort(key=lambda e: e[0])
        timestamps = [e[0] for e in evs]
        users = [e[1] for e in evs]
        types = [e[2] for e in evs]

        attempt_count = sum(1 for t in types if t in ("failed", "accepted"))
        failed_count = sum(1 for t in types if t == "failed")
        success_count = sum(1 for t in types if t == "accepted")
        invalid_count = sum(1 for t in types if t == "invalid" or t == "failed")

        fail_ratio = failed_count / attempt_count if attempt_count else 0.0
        invalid_user_ratio = invalid_count / len(evs) if evs else 0.0
        unique_usernames = len(set(users))

        gaps = [
            (timestamps[i + 1] - timestamps[i]).total_seconds()
            for i in range(len(timestamps) - 1)
        ]
        avg_gap = sum(gaps) / len(gaps) if gaps else float(window_seconds)

        second_counts = defaultdict(int)
        for t in timestamps:
            second_counts[int(t.timestamp())] += 1
        max_attempts_per_second = max(second_counts.values()) if second_counts else 0

        rows.append({
            "window_start": window.isoformat(),
            "src_ip": ip,
            "attempt_count": attempt_count,
            "failed_count": failed_count,
            "success_count": success_count,
            "fail_ratio": round(fail_ratio, 3),
            "unique_usernames": unique_usernames,
            "invalid_user_ratio": round(invalid_user_ratio, 3),
            "avg_seconds_between_attempts": round(avg_gap, 3),
            "max_attempts_per_second": max_attempts_per_second,
        })

    return rows


def main():
    ap = argparse.ArgumentParser(description="Parse SSH auth logs into feature rows")
    ap.add_argument("--input", nargs="+", default=None,
                     help="Log file(s) to parse. Defaults to raw_logs/*.log plus sample_auth.log if present.")
    ap.add_argument("--window-seconds", type=int, default=WINDOW_SECONDS)
    ap.add_argument("--output", default=os.path.join(os.path.dirname(__file__), "log_features.csv"))
    args = ap.parse_args()

    if args.input:
        input_files = args.input
    else:
        here = os.path.dirname(__file__)
        input_files = glob.glob(os.path.join(here, "raw_logs", "*.log"))
        sample = os.path.join(here, "sample_auth.log")
        if os.path.exists(sample):
            input_files.append(sample)

    if not input_files:
        raise SystemExit("No log files found. Run generate_sample_authlog.py or ssh_fetcher.py first.")

    print(f"Parsing {len(input_files)} file(s): {input_files}")

    all_events = []
    for path in input_files:
        all_events.extend(parse_log_file(path))

    print(f"Parsed {len(all_events)} raw auth events")

    rows = extract_features(all_events, args.window_seconds)
    print(f"Aggregated into {len(rows)} feature rows ({args.window_seconds}s windows)")

    import csv
    fieldnames = [
        "window_start", "src_ip", "attempt_count", "failed_count", "success_count",
        "fail_ratio", "unique_usernames", "invalid_user_ratio",
        "avg_seconds_between_attempts", "max_attempts_per_second",
    ]
    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved feature CSV -> {args.output}")


if __name__ == "__main__":
    main()
