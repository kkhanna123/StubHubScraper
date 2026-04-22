"""Category-page event discovery.

Scrapes the Mutua Madrid Open category page and returns the list of events
(sessions). StubHub embeds the full event grid as a JSON blob in an inline
<script> tag; we locate and parse it.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from .browser import browser_ctx, load_page_html
from .config import CATEGORY_URL, MANIFEST_PATH, SESSION_DURATION_HOURS

log = logging.getLogger(__name__)


@dataclass
class Event:
    event_id: int
    name: str
    url: str
    venue_name: str
    venue_city: str
    start_utc: datetime       # scheduled start time (UTC)
    end_utc: datetime         # inferred session end (UTC)
    category_id: int          # used as a CategoryId in the listings POST payload
    day_of_week: str
    formatted_date: str
    formatted_time: str

    @property
    def slug(self) -> str:
        """Filesystem-safe identifier carrying the UTC session time range.

        `start_utc` / `end_utc` are already UTC; the 'Z' suffix in the
        formatted window makes that explicit for downstream consumers.
        """
        ymd = self.start_utc.strftime("%Y%m%d")
        hm_start = self.start_utc.strftime("%H%M")
        hm_end = self.end_utc.strftime("%H%M")
        venue = re.sub(r"[^a-zA-Z0-9]+", "-", self.venue_name).strip("-").lower()[:40]
        return f"event_{self.event_id}_{ymd}_{hm_start}-{hm_end}Z_{venue}"

    def to_json(self) -> dict:
        return {
            "event_id": self.event_id,
            "name": self.name,
            "url": self.url,
            "venue_name": self.venue_name,
            "venue_city": self.venue_city,
            "start_utc": self.start_utc.isoformat(),
            "end_utc": self.end_utc.isoformat(),
            "category_id": self.category_id,
            "day_of_week": self.day_of_week,
            "formatted_date": self.formatted_date,
            "formatted_time": self.formatted_time,
        }

    @classmethod
    def from_json(cls, d: dict) -> "Event":
        return cls(
            event_id=d["event_id"],
            name=d["name"],
            url=d["url"],
            venue_name=d["venue_name"],
            venue_city=d["venue_city"],
            start_utc=datetime.fromisoformat(d["start_utc"]),
            end_utc=datetime.fromisoformat(d["end_utc"]),
            category_id=d["category_id"],
            day_of_week=d["day_of_week"],
            formatted_date=d["formatted_date"],
            formatted_time=d["formatted_time"],
        )


def _parse_state_script(html: str) -> dict:
    """Return the large JSON-payload inline script that carries eventGrids.

    StubHub emits its server-rendered Redux-like state as a raw JSON object
    inside a <script> tag (no variable assignment). We find the script that
    contains 'eventGrids' and parse it.
    """
    for m in re.finditer(r"<script[^>]*>(.*?)</script>", html, re.DOTALL):
        s = m.group(1)
        if "eventGrids" in s or ('"grid"' in s and "eventName" in s):
            try:
                return json.loads(s.strip())
            except Exception:
                continue
    raise ValueError("No StubHub state JSON found in page")


def _events_from_state(state: dict) -> Iterable[Event]:
    grids = state.get("eventGrids", {})
    for grid in grids.values():
        for item in grid.get("items", []):
            if not item.get("isDateConfirmed", True):
                continue
            meta = (item.get("eventMetadata") or {}).get("common") or {}
            start_ms = meta.get("eventStartDateTime")
            if not start_ms:
                continue
            # eventStartDateTime is a UTC epoch in ms
            start = datetime.fromtimestamp(int(start_ms) / 1000, tz=timezone.utc)
            end = start + timedelta(hours=SESSION_DURATION_HOURS)
            # Tournament / week-long passes have formattedTime like "14 days"; we
            # detect them and set end to the far end of the advertised window.
            ft = (item.get("formattedTime") or "").lower()
            if ft.endswith("days"):
                try:
                    days = int(ft.split()[0])
                    end = start + timedelta(days=days, hours=SESSION_DURATION_HOURS)
                except Exception:
                    pass
            yield Event(
                event_id=int(item["eventId"]),
                name=item["name"],
                url=item["url"],
                venue_name=item.get("venueName", ""),
                venue_city=item.get("venueCity", ""),
                start_utc=start,
                end_utc=end,
                category_id=int(state.get("parentCategoryId") or 4409),
                day_of_week=item.get("dayOfWeek", ""),
                formatted_date=item.get("formattedDate", ""),
                formatted_time=item.get("formattedTime", ""),
            )


def discover_events(ctx=None) -> list[Event]:
    """Fetch category page, return all parseable events."""
    if ctx is None:
        with browser_ctx() as ctx:
            return discover_events(ctx)
    html = load_page_html(ctx, CATEGORY_URL)
    state = _parse_state_script(html)
    events = list(_events_from_state(state))
    log.info("discovered %d events at %s", len(events), CATEGORY_URL)
    return events


def load_manifest(path: Path = MANIFEST_PATH) -> dict[int, Event]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {e["event_id"]: Event.from_json(e) for e in data}


def save_manifest(events: dict[int, Event], path: Path = MANIFEST_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = sorted(
        (e.to_json() for e in events.values()), key=lambda e: e["start_utc"]
    )
    path.write_text(json.dumps(payload, indent=2))


def refresh_manifest(ctx=None) -> dict[int, Event]:
    """Merge freshly-discovered events into the persisted manifest.

    Existing entries are updated in place (times can shift), new events added.
    Events that disappear from the category page are retained in the manifest
    so we keep collecting for sessions that move off the listing grid once
    they're imminent or in progress.
    """
    existing = load_manifest()
    fresh = {e.event_id: e for e in discover_events(ctx)}
    existing.update(fresh)
    save_manifest(existing)
    return existing
