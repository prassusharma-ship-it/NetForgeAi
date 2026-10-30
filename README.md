# SIH Prototype

## Quick start

From the project root:

```bash
python -m pip install -r requirements.txt
python run_demo.py
```

Then open `dashboard/index.html` in your browser. The launcher creates the synthetic traffic dataset and the netflow IsolationForest model if they do not already exist, then starts the API at `http://127.0.0.1:8000`.

In a second terminal, replay traffic:

```bash
python simulator/replay.py
```

The project uses paths relative to the project directory, so it no longer depends on `/home/claude/...` or any other machine-specific path.

### API smoke test

```bash
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/stats
```

To stop the backend, press `Ctrl+C` in the launcher terminal.

## Optional pipelines

### SSH log pipeline

```bash
python log_pipeline/generate_sample_authlog.py
python log_pipeline/log_parser.py
python ml/train_model_from_logs.py
```

### URL pipeline

The URL pipeline needs network access because it performs normal HTTP GET requests and TLS handshakes.

```bash
python url_pipeline/fetch_urls.py https://example.com https://www.python.org
python ml/train_model_from_urls.py
```

The URL analyzer is then available at `POST /analyze-url`.

## Pipeline A — netflow (unchanged)

```bash
python3 data/generate_synthetic_traffic.py
python3 ml/train_model.py
uvicorn backend.main:app --reload --port 8000     # separate terminal
python3 simulator/replay.py                        # separate terminal
# open dashboard/index.html in a browser
```

## Pipeline B — SSH/VPS log-based (new)

**Step 1 — get log data.** Either test offline first, or connect to a real server:

```bash
# Option 1: offline test (no server needed)
python3 log_pipeline/generate_sample_authlog.py

# Option 2: real server
cp log_pipeline/config.example.py log_pipeline/config.py   # edit with your host/user/key
cd log_pipeline && python3 fetch_all.py
# or a single host directly:
python3 log_pipeline/ssh_fetcher.py --host 1.2.3.4 --user root \
    --key-path ~/.ssh/id_rsa --remote-path /var/log/auth.log
```

**Step 2 — parse raw log text into feature columns:**

```bash
cd log_pipeline && python3 log_parser.py
```

This produces `log_pipeline/log_features.csv` with columns:
`window_start, src_ip, attempt_count, failed_count, success_count,
fail_ratio, unique_usernames, invalid_user_ratio,
avg_seconds_between_attempts, max_attempts_per_second`

Each row = one source IP's behavior in one 60-second window. This is the
"important features extracted from raw text logs" you asked for — ready
to train on directly.

**Step 3 — train on it:**

```bash
python3 ml/train_model_from_logs.py
```

Unsupervised (no labels needed) — it flags source IPs whose behavior
(attempt rate, fail ratio, burstiness) looks statistically different from
normal traffic. Prints which windows got flagged so you can sanity-check
against known attacker IPs before your demo.

## Pipeline C — URL-based (new)

**Step 1 — build a dataset by fetching some URLs:**

```bash
python3 url_pipeline/fetch_urls.py https://example.com https://another-site.com
# or from a watchlist file, one URL per line:
python3 url_pipeline/fetch_urls.py --file url_pipeline/watchlist.txt
```

This appends rows to `url_pipeline/url_features.csv` with columns:
`url_length, num_dots, num_hyphens, num_digits, num_subdomains, is_ip_host,
has_https, num_redirects, response_time_ms, status_code, content_length,
has_hsts, has_csp, has_xframe, cert_days_remaining` — plus human-readable
extras (`final_url`, `server_header`) for debugging.

Fetch at least 15-20 URLs (mix of sites) before training — IsolationForest
needs a real batch to learn what "normal" looks like.

**Step 2 — train:**

```bash
python3 ml/train_model_from_urls.py
```

Unsupervised, same as Pipeline B — no manual labeling. Prints which URLs
got flagged so you can sanity-check the result.

**Step 3 — use it live:** once trained, the backend's `POST /analyze-url`
endpoint and the dashboard's "Check a URL" box both work — paste any URL,
get an instant verdict (fetches live, scores against the trained model,
shows security headers + cert expiry + severity).

```bash
curl -X POST http://localhost:8000/analyze-url -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

**Ethical note:** this only performs a normal HTTP GET + TLS handshake —
the same data your browser gets when it loads a page. It doesn't probe
ports, brute force, or access anything not already served to any visitor.
Still, only point it at sites you own or are authorized to test/monitor.

## Connecting Pipeline B to the live backend/dashboard (next step)

Right now Pipeline B trains and evaluates standalone (prints results to
console). To wire it into the live dashboard like Pipeline A:
1. Add a `/ingest-log-window` endpoint in `backend/main.py`, mirroring
   `/ingest`, but using `AnomalyScorer(..., features=LOG_FEATURES)` from
   `ml/model.py` (already built to support this — just point it at
   `log_isolation_forest.joblib` / `log_scaler.joblib`).
2. Write a small script that reads new lines from `log_features.csv` (or
   re-runs `ssh_fetcher.py` + `log_parser.py` on a timer) and POSTs each
   row to that endpoint, same pattern as `simulator/replay.py`.

Happy to build that wiring if you want it before the deadline — just ask.

## Notes on realism

- Real auth.log format varies slightly by distro (Ubuntu/Debian:
  `/var/log/auth.log`; CentOS/RHEL: `/var/log/secure`) and by SSH config
  (key-based auth logs differently than password auth). The regex in
  `log_parser.py` handles the common password-auth case — if your VPS
  uses key-only auth, you'll see `Accepted publickey for ...` instead of
  `Accepted password for ...`; add that pattern to `ACCEPTED_RE` in
  `log_parser.py` if needed.
- `WINDOW_SECONDS = 60` in `log_parser.py` controls the aggregation
  window — shrink it for more granular (but noisier) features, widen it
  if your traffic volume is low.
- Storage is in-memory for the prototype. Swap in
  PostgreSQL/TimescaleDB for anything beyond a demo (marked with TODO
  comments in `backend/main.py`).
