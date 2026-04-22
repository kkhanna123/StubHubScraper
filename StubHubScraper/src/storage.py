"""Per-event parquet storage.

Each session gets one parquet file whose name encodes the UTC time range of
the advertised session, so consumers can interpolate against actual match
times later without needing the manifest:

    data/event_{eventId}_{yyyymmdd}_{HHMM}-{HHMM}Z_{venue-slug}.parquet

Snapshots append: we read any existing file, concat new rows, and rewrite.
Given typical volume (<100 listings × 14 days × 24h ≈ 33k rows per event),
full rewrites are cheap and avoid fragile parquet-append code paths.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .config import DATA_DIR
from .discovery import Event

log = logging.getLogger(__name__)


def event_parquet_path(event: Event) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / f"{event.slug}.parquet"


def append_rows(event: Event, rows: list[dict]) -> Path:
    """Append snapshot rows to the event's parquet file.

    Concurrent writers are not expected; this function performs a
    read-modify-write without locking.
    """
    if not rows:
        return event_parquet_path(event)
    path = event_parquet_path(event)
    new = pd.DataFrame(rows)
    if path.exists():
        existing = pd.read_parquet(path)
        combined = pd.concat([existing, new], ignore_index=True)
    else:
        combined = new
    combined.to_parquet(path, index=False)
    log.info("event %s: wrote %d new rows (total %d) -> %s",
             event.event_id, len(new), len(combined), path.name)
    return path
