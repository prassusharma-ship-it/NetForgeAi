"""
Connects to a remote VPS/server over SSH and pulls down log file content
(auth.log / secure / any text log) for local processing.

This is the "fetch log values from client and server connection via SSH"
piece of the pipeline. It does NOT parse or extract features -- that's
log_parser.py's job, on purpose, so you can re-run parsing/feature
extraction against saved raw logs without re-connecting every time.

Setup:
    pip install paramiko

Usage:
    python3 log_pipeline/ssh_fetcher.py --host 1.2.3.4 --user root \\
        --key-path ~/.ssh/id_rsa --remote-path /var/log/auth.log

    # or with password auth (fine for a hackathon VPS, use keys for anything real):
    python3 log_pipeline/ssh_fetcher.py --host 1.2.3.4 --user root \\
        --password mypass --remote-path /var/log/auth.log
"""

import argparse
import os
from datetime import datetime

import paramiko

RAW_LOG_DIR = os.path.join(os.path.dirname(__file__), "raw_logs")


def fetch_log(host, port, user, remote_path, key_path=None, password=None, tail_lines=5000):
    os.makedirs(RAW_LOG_DIR, exist_ok=True)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # fine for hackathon; use known_hosts for anything real

    connect_kwargs = {"hostname": host, "port": port, "username": user, "timeout": 10}
    if key_path:
        connect_kwargs["key_filename"] = os.path.expanduser(key_path)
    elif password:
        connect_kwargs["password"] = password
    else:
        raise ValueError("Provide either --key-path or --password")

    print(f"Connecting to {user}@{host}:{port} ...")
    client.connect(**connect_kwargs)

    command = f"tail -n {tail_lines} {remote_path}"
    print(f"Running: {command}")
    stdin, stdout, stderr = client.exec_command(command)

    output = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()

    if err.strip():
        print(f"[stderr from remote host]: {err.strip()}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_host = host.replace(".", "_")
    out_file = os.path.join(RAW_LOG_DIR, f"{safe_host}_{timestamp}.log")

    with open(out_file, "w") as f:
        f.write(output)

    print(f"Saved {len(output.splitlines())} lines -> {out_file}")
    return out_file


def main():
    parser = argparse.ArgumentParser(description="Fetch remote log file over SSH")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--user", required=True)
    parser.add_argument("--key-path", default=None, help="Path to SSH private key")
    parser.add_argument("--password", default=None, help="SSH password (use key-path instead where possible)")
    parser.add_argument("--remote-path", default="/var/log/auth.log",
                         help="Log file path on the remote host (e.g. /var/log/auth.log or /var/log/secure)")
    parser.add_argument("--tail-lines", type=int, default=5000)
    args = parser.parse_args()

    fetch_log(
        host=args.host, port=args.port, user=args.user,
        remote_path=args.remote_path, key_path=args.key_path,
        password=args.password, tail_lines=args.tail_lines,
    )


if __name__ == "__main__":
    main()
