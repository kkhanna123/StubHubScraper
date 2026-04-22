"""Fetch every listing for a single event via paginated POSTs.

The endpoint is the event page URL itself (POST). The browser context must be
warmed by a prior GET so WAF cookies are present; otherwise the POST is
rejected with 403.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .browser import post_json
from .config import MAX_PAGES, PAGE_SIZE, REQUEST_PAUSE_SEC

log = logging.getLogger(__name__)


def _payload(page: int, page_size: int, quantity: int, category_id: int) -> dict[str, Any]:
    """Build the JSON body StubHub's event-page POST endpoint expects.

    Captured verbatim from a Playwright-driven pagination click; all fields
    are kept because the endpoint silently returns {} if required fields are
    missing or have unexpected values (e.g. "NEWEST" vs "RECOMMENDED").
    """
    return {
        "ShowAllTickets": True,
        "HideDuplicateTicketsV2": False,
        "Quantity": quantity,
        "IsInitialQuantityChange": False,
        "PageVisitId": str(uuid.uuid4()).upper(),
        "PageSize": page_size,
        "CurrentPage": page,
        "SortBy": "RECOMMENDED",
        "SortDirection": 1,
        "Sections": "", "Rows": "", "Seats": "", "SeatTypes": "",
        "TicketClasses": "", "ListingNotes": "", "PriceRange": "",
        "InstantDelivery": False,
        "EstimatedFees": True,
        "BetterValueTickets": True,
        "PriceOption": "",
        "HasFlexiblePricing": False,
        "ExcludeSoldListings": False,
        "RemoveObstructedView": False,
        "NewListingsOnly": False,
        "PriceDropListingsOnly": False,
        "Favorites": False,
        "FilterSortSessionId": str(uuid.uuid4()).upper(),
        "Method": "IndexSh",
        "CategoryId": category_id,
        "IsDirectFromPaidSearch": False,
    }


@dataclass
class ListingsSnapshot:
    event_id: int
    snapshot_ts: datetime
    items: list[dict[str, Any]]     # raw listing dicts (one per unique listing id)
    total_count: int                # StubHub-reported totalCount for this filter
    min_price: float | None
    max_price: float | None


def fetch_listings(ctx, event_url: str, event_id: int, category_id: int,
                   page_size: int = PAGE_SIZE, max_pages: int = MAX_PAGES) -> ListingsSnapshot:
    """Collect every unique listing for one event.

    Iterates pages until we've collected `totalCount` unique listings, or
    `max_pages` is hit, or a page returns zero items. Items are deduped by
    `id` because successive pages occasionally overlap.
    """
    seen: dict[int, dict[str, Any]] = {}
    total = 0
    min_price = max_price = None
    url = event_url + ("&quantity=1" if "?" in event_url else "?quantity=1")
    for pg in range(1, max_pages + 1):
        resp = post_json(ctx, url, _payload(pg, page_size, 1, category_id), referer=url)
        items = resp.get("items") or []
        if not items and pg == 1:
            log.warning("event %s page 1 returned no items", event_id)
            break
        if not items:
            break
        for it in items:
            lid = it.get("id")
            if lid is None or lid in seen:
                continue
            seen[lid] = it
        total = resp.get("totalCount") or total
        if min_price is None or (resp.get("minPrice") is not None and resp["minPrice"] < min_price):
            min_price = resp.get("minPrice") or min_price
        if max_price is None or (resp.get("maxPrice") is not None and resp["maxPrice"] > max_price):
            max_price = resp.get("maxPrice") or max_price
        if total and len(seen) >= total:
            break
        time.sleep(REQUEST_PAUSE_SEC)
    return ListingsSnapshot(
        event_id=event_id,
        snapshot_ts=datetime.now(tz=timezone.utc),
        items=list(seen.values()),
        total_count=total or len(seen),
        min_price=min_price,
        max_price=max_price,
    )
