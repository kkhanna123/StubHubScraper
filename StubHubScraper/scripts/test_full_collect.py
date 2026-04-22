"""Collect every listing for one event via paginated POSTs. Verifies that a
single browser context can serve many events and handles pagination correctly."""
from playwright.sync_api import sync_playwright
import json, uuid, statistics

EVENT_URL = "https://www.stubhub.com/mutua-madrid-open-madrid-tickets-4-22-2026/event/158170204/?quantity=1"


def payload(page, page_size=100):
    return {
        "ShowAllTickets": True,
        "HideDuplicateTicketsV2": False,
        "Quantity": 1,
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
        "CategoryId": 4409,
        "IsDirectFromPaidSearch": False,
    }


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        viewport={"width": 1400, "height": 900},
        locale="en-US",
    )
    page = ctx.new_page()
    page.goto(EVENT_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    hdrs = {
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": EVENT_URL,
        "Origin": "https://www.stubhub.com",
    }

    # First try PageSize=100
    r = ctx.request.post(EVENT_URL, data=json.dumps(payload(1, 100)), headers=hdrs)
    j = r.json()
    print(f"page=1 size=100 -> items={len(j.get('items', []))} total={j.get('totalCount')}")

    # Paginate with whatever PageSize works
    page_size = 100 if len(j.get("items", [])) > 10 else 10
    all_items = {}
    for pg in range(1, 30):
        r = ctx.request.post(EVENT_URL, data=json.dumps(payload(pg, page_size)), headers=hdrs)
        j = r.json()
        items = j.get("items", [])
        new = 0
        for it in items:
            if it["id"] not in all_items:
                all_items[it["id"]] = it
                new += 1
        total = j.get("totalCount", 0)
        print(f"page={pg}: got={len(items)} new={new} unique={len(all_items)}/{total}")
        if not items or len(all_items) >= total:
            break

    print(f"\nCollected {len(all_items)} listings")
    prices = [it["rawPrice"] for it in all_items.values() if it.get("rawPrice")]
    qtys = [it["availableTickets"] for it in all_items.values() if it.get("availableTickets")]
    if prices:
        prices.sort()
        n = len(prices)
        mean = sum(prices) / n
        total_tickets = sum(qtys)
        vwap = (sum(it["rawPrice"] * it["availableTickets"] for it in all_items.values()) / total_tickets) if total_tickets else None
        p10 = prices[max(0, n // 10)]
        std = statistics.pstdev(prices) if n > 1 else 0
        print(f"\nPrice stats (USD):")
        print(f"  count: {n}")
        print(f"  total tickets: {total_tickets}")
        print(f"  min: ${prices[0]:.2f}  median: ${prices[n // 2]:.2f}  max: ${prices[-1]:.2f}")
        print(f"  mean: ${mean:.2f}  vwap: ${vwap:.2f}  p10: ${p10:.2f}  std: ${std:.2f}")
        print(f"  spread proxy (p10 - min): ${p10 - prices[0]:.2f}")

    browser.close()
