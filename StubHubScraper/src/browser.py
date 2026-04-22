"""Playwright context helpers. Used for both event discovery (HTML parse) and
listings fetch (authenticated POST from inside the browser context)."""
from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from typing import Any

from playwright.sync_api import BrowserContext, sync_playwright

from .config import USER_AGENT

log = logging.getLogger(__name__)


@contextmanager
def browser_ctx():
    """Yield a fresh Playwright BrowserContext.

    The context holds cookies set by StubHub's WAF after the first page load,
    which are required for subsequent POSTs to the listings endpoint to
    succeed. Without warming the context by visiting a real page first, the
    POST is rejected with 403.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1400, "height": 900},
            locale="en-US",
        )
        try:
            yield ctx
        finally:
            browser.close()


def load_page_html(ctx: BrowserContext, url: str, settle_ms: int = 3000) -> str:
    """Load `url` in a real page (to set WAF cookies on the context) and
    return the server's raw HTML body.

    We use the navigation Response body rather than `page.content()` because
    StubHub wipes the server-rendered state JSON from the DOM once React
    hydrates, so `page.content()` no longer contains the `eventGrids` /
    `grid` blobs we need to parse.
    """
    page = ctx.new_page()
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(settle_ms)
        if resp is not None:
            try:
                body = resp.body().decode("utf-8", errors="replace")
                if body:
                    return body
            except Exception as e:
                log.warning("goto response body unavailable, falling back to DOM: %s", e)
        return page.content()
    finally:
        page.close()


def post_json(ctx: BrowserContext, url: str, payload: dict[str, Any],
              referer: str | None = None, retries: int = 2) -> dict[str, Any]:
    """POST JSON to `url` from within the browser context and return parsed JSON.

    Returns an empty dict on failure after retries.
    """
    hdrs = {
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": referer or url,
        "Origin": "https://www.stubhub.com",
    }
    body = json.dumps(payload)
    for attempt in range(retries + 1):
        try:
            r = ctx.request.post(url, data=body, headers=hdrs, timeout=30_000)
            if r.status == 200:
                txt = r.text()
                if txt:
                    return json.loads(txt)
                return {}
            log.warning("POST %s -> %d (attempt %d)", url, r.status, attempt)
        except Exception as e:
            log.warning("POST error on %s: %s (attempt %d)", url, e, attempt)
        time.sleep(1.5 * (attempt + 1))
    return {}
