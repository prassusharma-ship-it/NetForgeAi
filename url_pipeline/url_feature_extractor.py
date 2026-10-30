"""
Given just a URL, fetches it and extracts a row of numeric feature
columns -- no SSH, no server access needed, just the URL.

This is the "tell me the URL, you fetch the details" pipeline. Everything
here is a passive HTTP request + a TLS handshake -- the same data your
browser already sees when it loads the page. It does not probe ports,
brute force anything, or touch content you're not already being served.
Only point this at sites you own or are authorized to test/monitor.

Fields fetched:
    - HTTP: status code, response time, redirect chain, content length,
      security-relevant headers (HSTS, CSP, X-Frame-Options)
    - TLS: certificate issuer, days until expiry (HTTPS sites only)
    - URL structure: length, dot/hyphen/digit counts, subdomain count,
      whether the host is a raw IP (all of these are standard signals
      used in malicious-URL-detection literature/datasets)

Usage as a library:
    from url_feature_extractor import extract_features
    row = extract_features("https://example.com")

Usage as a CLI (single URL, prints the row):
    python3 url_feature_extractor.py https://example.com
"""

import re
import socket
import ssl
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

TIMEOUT_SECONDS = 8
USER_AGENT = "Mozilla/5.0 (compatible; SIH-Prototype-Scanner/1.0)"

# The full ordered list of numeric columns this module produces --
# matches ml/model.py's URL_FEATURES so the two stay in sync.
FEATURE_COLUMNS = [
    "url_length", "num_dots", "num_hyphens", "num_digits", "num_subdomains",
    "is_ip_host", "has_https", "num_redirects", "response_time_ms",
    "status_code", "content_length", "has_hsts", "has_csp", "has_xframe",
    "cert_days_remaining",
]

IP_HOST_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def _url_structure_features(url: str) -> dict:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    return {
        "url_length": len(url),
        "num_dots": url.count("."),
        "num_hyphens": url.count("-"),
        "num_digits": sum(c.isdigit() for c in url),
        "num_subdomains": max(host.count(".") - 1, 0),
        "is_ip_host": 1 if IP_HOST_RE.match(host) else 0,
        "has_https": 1 if parsed.scheme == "https" else 0,
    }


def _cert_days_remaining(hostname: str, port: int = 443) -> float:
    """Returns days until TLS cert expiry, or -1 if unavailable (e.g. plain HTTP)."""
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=TIMEOUT_SECONDS) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
        expiry = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
        expiry = expiry.replace(tzinfo=timezone.utc)
        remaining = (expiry - datetime.now(timezone.utc)).total_seconds() / 86400
        return round(remaining, 1)
    except Exception:
        return -1.0


def extract_features(url: str, timeout: int = TIMEOUT_SECONDS) -> dict:
    """
    Fetches `url` and returns a flat dict of numeric features plus a few
    human-readable extras (final_url, server_header) for display/logging.
    Never raises for ordinary fetch failures -- returns a row with
    fetch_error set instead, so batch runs over many URLs don't die on one bad host.
    """
    row = {"url": url, "fetched_at": datetime.now(timezone.utc).isoformat(), "fetch_error": None}
    row.update(_url_structure_features(url))

    try:
        start = time.perf_counter()
        resp = requests.get(
            url, timeout=timeout, allow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        headers = {k.lower(): v for k, v in resp.headers.items()}
        row.update({
            "num_redirects": len(resp.history),
            "response_time_ms": round(elapsed_ms, 1),
            "status_code": resp.status_code,
            "content_length": len(resp.content),
            "has_hsts": 1 if "strict-transport-security" in headers else 0,
            "has_csp": 1 if "content-security-policy" in headers else 0,
            "has_xframe": 1 if "x-frame-options" in headers else 0,
            "final_url": resp.url,
            "server_header": headers.get("server", "unknown"),
        })

        parsed_final = urlparse(resp.url)
        if parsed_final.scheme == "https":
            row["cert_days_remaining"] = _cert_days_remaining(parsed_final.hostname)
        else:
            row["cert_days_remaining"] = -1.0

    except requests.RequestException as e:
        row["fetch_error"] = str(e)
        # fill defaults so this row is still usable/trainable despite the failure
        row.update({
            "num_redirects": -1, "response_time_ms": -1, "status_code": -1,
            "content_length": -1, "has_hsts": 0, "has_csp": 0, "has_xframe": 0,
            "final_url": url, "server_header": "unknown", "cert_days_remaining": -1.0,
        })

    return row


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 url_feature_extractor.py <url>")
        sys.exit(1)

    url = sys.argv[1]
    row = extract_features(url)
    for k, v in row.items():
        print(f"{k:24s} {v}")


if __name__ == "__main__":
    main()
