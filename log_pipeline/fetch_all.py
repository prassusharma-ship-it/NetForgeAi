"""
Loops over every server in config.py and fetches its log file via SSH.

Usage:
    cp log_pipeline/config.example.py log_pipeline/config.py   # then edit it
    python3 log_pipeline/fetch_all.py
"""

from ssh_fetcher import fetch_log

try:
    from config import SERVERS
except ImportError:
    raise SystemExit(
        "Missing log_pipeline/config.py -- copy config.example.py to config.py "
        "and fill in your server details first."
    )


def main():
    fetched_files = []
    for server in SERVERS:
        try:
            path = fetch_log(
                host=server["host"],
                port=server.get("port", 22),
                user=server["user"],
                remote_path=server.get("remote_path", "/var/log/auth.log"),
                key_path=server.get("key_path"),
                password=server.get("password"),
                tail_lines=server.get("tail_lines", 5000),
            )
            fetched_files.append(path)
        except Exception as e:
            print(f"Failed to fetch from {server['host']}: {e}")

    print(f"\nFetched {len(fetched_files)} log file(s):")
    for f in fetched_files:
        print(f"  - {f}")
    print("\nNext: python3 log_pipeline/log_parser.py")


if __name__ == "__main__":
    main()
