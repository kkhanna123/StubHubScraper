"""Verify: after loading an event page in Playwright (warming WAF cookies),
can we POST the listings JSON directly via page.request? Single page.goto +
N POSTs is the ideal runtime pattern."""
from playwright.sync_api import sync_playwright
import json, uuid

EVENT_URL = "https://www.stubhub.com/mutua-madrid-open-madrid-tickets-4-22-2026/event/158170204/?quantity=1"


def build_payload(page=1, page_size=10, quantity=1, category_id=4409):
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
        "Sections": "",
        "Rows": "",
        "Seats": "",
        "SeatTypes": "",
        "TicketClasses": "",
        "ListingNotes": "",
        "PriceRange": "",
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


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        viewport={"width": 1400, "height": 900},
        locale="en-US",
    )
    page = ctx.new_page()

    print("Loading event page to warm cookies...")
    page.goto(EVENT_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)

    print(f"\ncookies: {len(ctx.cookies())}")
    # Use page.request which inherits the context (cookies + tls fingerprint)
    print("POSTing listings fetch directly via browser context...")
    payload = build_payload(page=1, page_size=10)
    r = ctx.request.post(
        EVENT_URL,
        data=json.dumps(payload),
        headers={
            "Content-Type": "application/json;charset=UTF-8",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": EVENT_URL,
            "Origin": "https://www.stubhub.com",
        },
    )
    print(f"status: {r.status}")
    body = r.text()
    print(f"len: {len(body)}")
    print(f"head: {body[:300]}")
    try:
        j = json.loads(body)
        print("\n=== RESULT ===")
        print("items:", len(j.get("items", [])))
        print("totalCount:", j.get("totalCount"))
        print("totalFilteredListings:", j.get("totalFilteredListings"))
        print("minPrice/maxPrice:", j.get("minPrice"), j.get("maxPrice"))
        if j.get("items"):
            it = j["items"][0]
            print("\nFirst item subset:")
            for k in ("id", "rawPrice", "availableTickets", "section", "row",
                      "ticketClassName", "listingTypeId", "faceValue", "createdDateTime"):
                print(f"  {k}: {it.get(k)!r}")
    except Exception as e:
        print("parse failed:", e)

    browser.close()
