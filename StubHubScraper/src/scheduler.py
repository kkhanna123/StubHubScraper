"""Hourly collection loop.

Cycle:
  1. Open a Playwright context.
  2. Refresh the event manifest from the category page.
  3. For every event whose `end_utc` is in the future: warm cookies on the
     event page, fetch all listings, compute summary, append rows.
  4. Close the context, sleep until next hour boundary, repeat.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from .browser import browser_ctx, load_page_html
from .config import CYCLE_INTERVAL_SEC, EVENT_PAUSE_SEC
from .discovery import Event, refresh_manifest
from .listings import fetch_listings
from .metrics import listing_rows, summary_row
from .storage import append_rows

log = logging.getLogger(__name__)


def collect_one_event(ctx, event: Event) -> int:
    """Return number of listings collected, or 0 on failure."""
    try:
        # Warm the browser context with a GET on the event page so WAF cookies
        # bind to this URL; the subsequent POST against the same URL inherits
        # them.
        load_page_html(ctx, event.url, settle_ms=1500)
    except Exception as e:
        log.error("event %s: page load failed: %s", event.event_id, e)
        return 0

    try:
        snap = fetch_listings(ctx, event.url, event.event_id, event.category_id)
    except Exception as e:
        log.error("event %s: listings fetch failed: %s", event.event_id, e)
        return 0

    rows = listing_rows(snap) + [summary_row(snap)]
    append_rows(event, rows)
    return len(snap.items)


def run_cycle() -> None:
    now = datetime.now(tz=timezone.utc)
    with browser_ctx() as ctx:
        manifest = refresh_manifest(ctx)
        live = [e for e in manifest.values() if e.end_utc > now]
        log.info("cycle %s: %d events in manifest, %d live",
                 now.isoformat(timespec="minutes"), len(manifest), len(live))

        for ev in sorted(live, key=lambda e: e.start_utc):
            log.info("collecting event %s (%s %s)", ev.event_id, ev.formatted_date, ev.formatted_time)
            n = collect_one_event(ctx, ev)
            log.info(" -> %d listings", n)
            time.sleep(EVENT_PAUSE_SEC)


def run_forever() -> None:
    while True:
        start = time.time()
        try:
            run_cycle()
        except Exception:
            log.exception("run_cycle crashed; continuing")
        elapsed = time.time() - start
        sleep_for = max(60, CYCLE_INTERVAL_SEC - elapsed)
        log.info("cycle done in %.1fs; sleeping %.0fs", elapsed, sleep_for)
        time.sleep(sleep_for)
