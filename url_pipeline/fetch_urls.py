"""
Runs url_feature_extractor.py over a list of URLs and appends one feature
row per URL to url_pipeline/url_features.csv -- this is your training
dataset builder for the URL pipeline.

Usage:
    # one-off, from the command line
    python3 url_pipeline/fetch_urls.py https://example.com https://another-site.com

    # or from a text file, one URL per line
    python3 url_pipeline/fetch_urls.py --file url_pipeline/watchlist.txt

Run this periodically (cron, or a loop with a sleep) against a watchlist
to build up a real dataset of "what normal looks like" for the sites you
care about, before layering anomaly detection on top.
"""

import argparse
import csv
import os

from url_feature_extractor import extract_features, FEATURE_COLUMNS

OUT_PATH = os.path.join(os.path.dirname(__file__), "url_features.csv")

# columns written to CSV: the trainable numeric features, plus a few
# human-readable extras useful for debugging/demo, in a fixed order.
CSV_COLUMNS = ["url", "fetched_at", "fetch_error", "final_url", "server_header"] + FEATURE_COLUMNS


def load_urls_from_file(path: str) -> list[str]:
    with open(path) as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]


def append_rows(rows: list[dict]):
    file_exists = os.path.exists(OUT_PATH)
    with open(OUT_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in CSV_COLUMNS})


def main():
    ap = argparse.ArgumentParser(description="Fetch and log features for a list of URLs")
    ap.add_argument("urls", nargs="*", help="One or more URLs to fetch")
    ap.add_argument("--file", help="Text file with one URL per line")
    args = ap.parse_args()

    urls = list(args.urls)
    if args.file:
        urls += load_urls_from_file(args.file)

    if not urls:
        raise SystemExit("Provide at least one URL, or --file <path>.")

    rows = []
    for url in urls:
        print(f"Fetching {url} ...")
        row = extract_features(url)
        status = "ERROR: " + row["fetch_error"] if row["fetch_error"] else f"status={row['status_code']}"
        print(f"  -> {status}, response_time_ms={row['response_time_ms']}")
        rows.append(row)

    append_rows(rows)
    print(f"\nAppended {len(rows)} row(s) -> {OUT_PATH}")


if __name__ == "__main__":
    main()
