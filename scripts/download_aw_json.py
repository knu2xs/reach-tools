"""
Download raw JSON for American Whitewater reaches 1-2000 from the tRPC API and
save each valid reach as references/aw_json/reach_XXXXXX.json.

Usage (from project root):
    python scripts/download_aw_json.py

Features:
- Concurrent downloads via ThreadPoolExecutor (5 workers)
- Skips already-downloaded files (safe to re-run / resume)
- Retries transient errors up to 3x with exponential backoff
- Respects HTTP 429 Retry-After header (outside retry budget)
- Atomic file writes (temp file + rename) prevent corrupt output on interrupt
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_URL = "https://trpc-api.americanwhitewater.org/reach/reachDetailWithPhotos"
OUT_DIR = Path(__file__).parent.parent / "references" / "aw_json"
ID_RANGE = range(1, 2001)
MAX_WORKERS = 5
MAX_RETRIES = 3
BACKOFF_BASE = 2          # seconds — attempt n waits BACKOFF_BASE ** n seconds
RATE_LIMIT_DEFAULT_WAIT = 30  # seconds — fallback when Retry-After header absent

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 10  # seconds per request


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_valid_response(data: list) -> bool:
    """Return True if the tRPC response contains a non-null reach payload."""
    try:
        return data[0]["result"]["data"]["json"] is not None
    except (KeyError, IndexError, TypeError):
        return False


def _write_atomic(path: Path, text: str) -> None:
    """Write text to path atomically using a temp file + rename (POSIX-safe)."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.rename(path)


# ---------------------------------------------------------------------------
# Per-reach worker
# ---------------------------------------------------------------------------

def _fetch_one(reach_id: int) -> dict:
    """
    Fetch one reach ID from the AW tRPC API and write to disk if valid.

    Returns a dict with keys:
        reach_id (int), outcome (str), message (str | None)

    Outcomes: "saved" | "skipped-exists" | "skipped-invalid" | "error"
    """
    output_path = OUT_DIR / f"reach_{reach_id:06d}.json"

    # T009 (US2): skip if already downloaded
    if output_path.exists():
        return {"reach_id": reach_id, "outcome": "skipped-exists", "message": None}

    params = {
        "batch": "1",
        "input": json.dumps({"0": {"json": {"reachID": str(reach_id)}}}),
    }

    attempt = 0
    last_error = None

    while True:
        try:
            resp = requests.get(
                API_URL,
                params=params,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
            )

            # T007 (US1): HTTP 429 — rate limited; respect Retry-After
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", RATE_LIMIT_DEFAULT_WAIT))
                time.sleep(wait)
                continue  # does NOT consume retry budget

            # T006 (US1): HTTP 404 — reach does not exist
            if resp.status_code == 404:
                return {"reach_id": reach_id, "outcome": "skipped-invalid", "message": "HTTP 404"}

            # Transient error — non-200 (excluding 404/429)
            if resp.status_code != 200 or not resp.content:
                raise ValueError(f"HTTP {resp.status_code}, content length {len(resp.content)}")

            # Parse response
            data = resp.json()

            # T008 (US1): validity check
            if not _is_valid_response(data):
                return {"reach_id": reach_id, "outcome": "skipped-invalid", "message": "null payload"}

            # Valid — write atomically
            _write_atomic(output_path, resp.text)
            return {"reach_id": reach_id, "outcome": "saved", "message": None}

        except Exception as exc:
            last_error = str(exc)
            attempt += 1
            if attempt >= MAX_RETRIES:
                return {"reach_id": reach_id, "outcome": "error", "message": last_error}
            time.sleep(BACKOFF_BASE ** attempt)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Download all valid AW reaches 1-2000 into references/aw_json/."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    jobs = list(ID_RANGE)
    counters = {"saved": 0, "skipped-exists": 0, "skipped-invalid": 0, "error": 0}

    print(f"Downloading AW reaches {jobs[0]}\u2013{jobs[-1]} \u2192 {OUT_DIR}")

    with tqdm(total=len(jobs), unit="reach") as pbar:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(_fetch_one, rid): rid for rid in jobs}
            for future in as_completed(futures):
                result = future.result()
                outcome = result["outcome"]
                counters[outcome] = counters.get(outcome, 0) + 1

                label = {
                    "saved": "Saved          ",
                    "skipped-exists": "Skipped (exists)",
                    "skipped-invalid": "Skipped (invalid)",
                    "error": "Error          ",
                }.get(outcome, outcome)

                msg = f"  {label}: reach_{result['reach_id']:06d}"
                if result.get("message"):
                    msg += f"  [{result['message']}]"
                tqdm.write(msg)
                pbar.update(1)

    # T012 (US3): final summary
    print(
        f"\nSummary: {counters['saved']} saved, "
        f"{counters['skipped-invalid']} skipped (invalid), "
        f"{counters['skipped-exists']} skipped (exists), "
        f"{counters.get('error', 0)} errors"
    )


if __name__ == "__main__":
    main()
