"""Turn raw listing dicts into tabular rows + summary metrics.

Two row types per snapshot:

  * listings rows — one per active listing (wide, raw-ish).
  * summary row   — one per event per snapshot, carries liquidity & price stats.

Both schemas are flat so they can live side-by-side in one parquet file per
event (summary rows are marked with row_type == "summary").
"""
from __future__ import annotations

import statistics
from datetime import datetime
from typing import Any

from .listings import ListingsSnapshot


def _pct(values: list[float], p: float) -> float | None:
    """Linear-interpolated percentile (p in [0,100]). Returns None if empty."""
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (p / 100.0)
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    frac = k - lo
    return s[lo] + (s[hi] - s[lo]) * frac


def listing_rows(snap: ListingsSnapshot) -> list[dict[str, Any]]:
    """One row per listing, denormalised for analytics."""
    ts = snap.snapshot_ts
    rows = []
    for it in snap.items:
        rows.append({
            "row_type": "listing",
            "snapshot_ts": ts,
            "event_id": snap.event_id,
            "listing_id": it.get("id"),
            "section": it.get("section"),
            "section_id": it.get("sectionId"),
            "row": it.get("row"),
            "ticket_class": it.get("ticketClassName"),
            "ticket_class_id": it.get("ticketClass"),
            "quantity_available": it.get("availableTickets"),
            "max_quantity": it.get("maxQuantity"),
            "raw_price_usd": it.get("rawPrice"),         # buyer-facing, incl. fees
            "face_value": it.get("faceValue"),
            "face_value_ccy": it.get("faceValueCurrencyCode"),
            "listing_currency": it.get("listingCurrencyCode"),
            "deal_score": it.get("formattedDealScore"),
            "is_cheapest": bool(it.get("isCheapestListing")),
            "is_best_deal": bool(it.get("showBestDealTag")),
            "is_sponsored": bool(it.get("isSponsored")),
            "listing_type_id": it.get("listingTypeId"),
            "ticket_type_id": it.get("ticketTypeId"),
            "created_dt": it.get("createdDateTime"),
            "listing_impression_id": it.get("listingImpressionId"),
            # summary-only fields kept null on listing rows
            "avg_price_usd": None,
            "vwap_usd": None,
            "median_price_usd": None,
            "price_std_usd": None,
            "min_price_usd": None,
            "max_price_usd": None,
            "p10_price_usd": None,
            "spread_proxy_usd": None,
            "listing_count": None,
            "total_quantity": None,
        })
    return rows


def summary_row(snap: ListingsSnapshot) -> dict[str, Any]:
    """One row per (event, snapshot) carrying aggregate stats & liquidity."""
    prices = [it["rawPrice"] for it in snap.items if it.get("rawPrice") is not None]
    qtys = [it.get("availableTickets") or 0 for it in snap.items]
    total_q = sum(qtys)
    avg = sum(prices) / len(prices) if prices else None
    vwap = (
        sum((it.get("rawPrice") or 0) * (it.get("availableTickets") or 0)
            for it in snap.items) / total_q
        if total_q else None
    )
    std = statistics.pstdev(prices) if len(prices) > 1 else 0.0 if prices else None
    median = statistics.median(prices) if prices else None
    mn = min(prices) if prices else None
    mx = max(prices) if prices else None
    p10 = _pct(prices, 10)
    spread = (p10 - mn) if (p10 is not None and mn is not None) else None
    return {
        "row_type": "summary",
        "snapshot_ts": snap.snapshot_ts,
        "event_id": snap.event_id,
        "listing_id": None,
        "section": None, "section_id": None, "row": None,
        "ticket_class": None, "ticket_class_id": None,
        "quantity_available": None, "max_quantity": None,
        "raw_price_usd": None, "face_value": None, "face_value_ccy": None,
        "listing_currency": None, "deal_score": None,
        "is_cheapest": None, "is_best_deal": None, "is_sponsored": None,
        "listing_type_id": None, "ticket_type_id": None,
        "created_dt": None, "listing_impression_id": None,
        "avg_price_usd": avg,
        "vwap_usd": vwap,
        "median_price_usd": median,
        "price_std_usd": std,
        "min_price_usd": mn,
        "max_price_usd": mx,
        "p10_price_usd": p10,
        "spread_proxy_usd": spread,
        "listing_count": len(snap.items),
        "total_quantity": total_q,
    }
