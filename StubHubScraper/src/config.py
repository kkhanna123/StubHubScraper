"""Scraper configuration."""
from pathlib import Path

CATEGORY_URL = "https://www.stubhub.com/mutua-madrid-open-tickets/category/138278297"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Tennis sessions advertise a start time but no end time. Assume a session is
# "live" until this many hours after scheduled start, then stop collecting.
# Mutua Madrid Open day sessions typically run 4-8 hours; pad generously.
SESSION_DURATION_HOURS = 10

PAGE_SIZE = 10        # StubHub caps effective page size at ~10 for this endpoint
MAX_PAGES = 30        # hard ceiling per event (events rarely exceed ~200 listings)
REQUEST_PAUSE_SEC = 0.5     # between POSTs to one event
EVENT_PAUSE_SEC = 2.0       # between events
CYCLE_INTERVAL_SEC = 3600   # hourly

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"
MANIFEST_PATH = DATA_DIR / "events_manifest.json"
