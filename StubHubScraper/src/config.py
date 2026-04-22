"""Scraper configuration."""
from __future__ import annotations

import os
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    return float(raw)


ROOT = Path(__file__).resolve().parent.parent

CATEGORY_URL = os.getenv(
    "STUBHUB_CATEGORY_URL",
    "https://www.stubhub.com/mutua-madrid-open-tickets/category/138278297",
)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Tennis sessions advertise a start time but no end time. Assume a session is
# "live" until this many hours after scheduled start, then stop collecting.
# Mutua Madrid Open day sessions typically run 4-8 hours; pad generously.
SESSION_DURATION_HOURS = _env_int("STUBHUB_SESSION_DURATION_HOURS", 10)

PAGE_SIZE = _env_int("STUBHUB_PAGE_SIZE", 10)  # StubHub caps effective page size at ~10 for this endpoint
MAX_PAGES = _env_int("STUBHUB_MAX_PAGES", 30)  # hard ceiling per event (events rarely exceed ~200 listings)
REQUEST_PAUSE_SEC = _env_float("STUBHUB_REQUEST_PAUSE_SEC", 0.5)
EVENT_PAUSE_SEC = _env_float("STUBHUB_EVENT_PAUSE_SEC", 2.0)
CYCLE_INTERVAL_SEC = _env_int("STUBHUB_CYCLE_INTERVAL_SEC", 3600)

DATA_DIR = Path(os.getenv("STUBHUB_DATA_DIR", str(ROOT / "data")))
LOG_DIR = Path(os.getenv("STUBHUB_LOG_DIR", str(ROOT / "logs")))
MANIFEST_PATH = DATA_DIR / os.getenv("STUBHUB_MANIFEST_FILENAME", "events_manifest.json")

STORAGE_BACKEND = os.getenv("STUBHUB_STORAGE_BACKEND", "parquet").strip().lower()
DUCKDB_PATH = Path(os.getenv("STUBHUB_DUCKDB_PATH", str(DATA_DIR / "stubhub.duckdb")))
DUCKDB_TABLE = os.getenv("STUBHUB_DUCKDB_TABLE", "stubhub_listings")
