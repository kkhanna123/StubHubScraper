"""One-shot: open an event page, click through pagination, and log every XHR URL
so we can identify the listings endpoint and required headers."""
from playwright.sync_api import sync_playwright
import json

EVENT_URL = "https://www.stubhub.com/mutua-madrid-open-madrid-tickets-4-22-2026/event/158170204/?quantity=1"
CATEGORY_URL = "https://www.stubhub.com/mutua-madrid-open-tickets/category/138278297"

requests_log = []


def on_request(req):
    if req.resource_type in {"xhr", "fetch"}:
        requests_log.append({
            "method": req.method,
            "url": req.url,
            "headers": dict(req.headers),
            "post_data": req.post_data,
        })


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        viewport={"width": 1400, "height": 900},
        locale="en-US",
    )
    page = ctx.new_page()
    page.on("request", on_request)

    print("=== Loading event page ===")
    page.goto(EVENT_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)

    # Try to scroll + click pagination to trigger XHR
    try:
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(1500)
        # Change quantity to 1 and re-sort to force re-fetch
        buttons = page.locator("button, a").all()
        for b in buttons[:200]:
            try:
                t = (b.inner_text() or "").strip().lower()
                if t in {"2", "next", "load more", "show more"}:
                    b.click(timeout=1500)
                    page.wait_for_timeout(1500)
                    break
            except Exception:
                continue
    except Exception as e:
        print("interaction err:", e)

    page.wait_for_timeout(2000)

    print("\n=== Loading category page ===")
    page.goto(CATEGORY_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)
    page.mouse.wheel(0, 8000)
    page.wait_for_timeout(2000)

    browser.close()

# Persist for analysis
out = "/tmp/xhr_capture.json"
with open(out, "w") as f:
    json.dump(requests_log, f, indent=2, default=str)
print(f"\n{len(requests_log)} XHR requests captured → {out}")
# print interesting ones
for r in requests_log:
    u = r["url"]
    if any(k in u.lower() for k in ["listing", "grid", "event", "page", "category", "tickets"]):
        print(f'  {r["method"]} {u[:180]}')
