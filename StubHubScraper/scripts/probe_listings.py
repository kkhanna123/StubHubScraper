"""Probe: open event page in Playwright, click through all pagination,
and log each network response that returns JSON with a 'grid' / listings
structure. This tells us whether pagination fires an XHR and what that
endpoint's URL + payload look like."""
from playwright.sync_api import sync_playwright
import json

EVENT_URL = "https://www.stubhub.com/mutua-madrid-open-madrid-tickets-4-22-2026/event/158170204/?quantity=1"

responses = []


def on_response(resp):
    try:
        if "application/json" not in (resp.headers.get("content-type") or ""):
            return
        if "stubhub.com" not in resp.url:
            return
        body = resp.text()
        if any(k in body for k in ['"rawPrice"', '"listingPrice"', '"gridListings"', '"items":[{"id":']):
            responses.append({
                "url": resp.url,
                "status": resp.status,
                "req_method": resp.request.method,
                "req_post": resp.request.post_data,
                "body_head": body[:500],
                "body_len": len(body),
            })
    except Exception:
        pass


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        viewport={"width": 1400, "height": 900},
        locale="en-US",
    )
    page = ctx.new_page()
    page.on("response", on_response)

    page.goto(EVENT_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(4000)

    # Dismiss any modal/cookie banner
    for sel in ['[id*="onetrust"] button', 'button:has-text("Accept")',
                'button:has-text("Got it")', 'button:has-text("Close")',
                '[aria-label="Close"]', '#modal-root button']:
        try:
            loc = page.locator(sel).first
            if loc.count():
                loc.click(timeout=1500, force=True)
                print(f"dismissed {sel}")
                page.wait_for_timeout(500)
        except Exception:
            pass

    # Scroll down to listings
    page.mouse.wheel(0, 3000)
    page.wait_for_timeout(1500)

    # Try to find pagination button + force click
    for attempt in range(6):
        page.mouse.wheel(0, 2500)
        page.wait_for_timeout(1200)
        candidates = page.locator(
            'button:has-text("Next"), button[aria-label*="next" i], '
            'a:has-text("Next"), button:has-text("Show more"), '
            'button:has-text("Load more")'
        )
        if not candidates.count():
            continue
        try:
            candidates.first.click(timeout=2500, force=True)
            print(f"clicked pagination #{attempt}")
            page.wait_for_timeout(2500)
        except Exception as e:
            print(f"click {attempt} err: {str(e)[:120]}")

    browser.close()

print(f"\n{len(responses)} JSON responses with listings-like body:")
for r in responses:
    print(f'  {r["req_method"]} {r["url"][:140]} status={r["status"]} len={r["body_len"]}')
    if r["req_post"]:
        print(f'    POST: {r["req_post"][:200]}')

with open("/tmp/listings_xhr.json", "w") as f:
    json.dump(responses, f, indent=2)
