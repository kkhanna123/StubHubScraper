# StubHub Madrid Open scraper

Hourly collection of every live ticket listing for the Mutua Madrid Open from [stubhub.com](https://www.stubhub.com/mutua-madrid-open-tickets/category/138278297), with per-listing snapshots and per-snapshot summary statistics (average price + liquidity).

Built to run 24/7 on a server for the duration of the tournament; sessions drop out automatically once their scheduled end time has passed.

---

## How it works

### 1. Session discovery

StubHub server-renders the category page with the full event grid embedded as a raw-JSON `<script>` blob. The scraper loads the page in a headless Chromium via Playwright, pulls the navigation response body (pre-hydration, so the blob is still present), and parses `eventGrids[*].items` to build the session manifest.

Each discovered session is persisted to `data/events_manifest.json` with its UTC start/end, venue, and the `categoryId` required for the listings POST. Subsequent cycles **merge** new sessions in and **keep** ones that have rolled off the grid, so in-progress events keep getting polled.

### 2. Listings fetch

StubHub's listings endpoint is `POST` to the event page URL itself, with a specific JSON body (see `src/listings.py::_payload` — the payload is reverse-engineered verbatim from a Playwright-driven pagination click; changing fields silently yields `{}`).

The endpoint is protected by an AWS WAF that 403s bare `curl`/`requests` calls, so every POST is issued **from inside the Playwright browser context** after a warm-up GET on the event page (which binds WAF cookies to the context). Listings are paginated at 10 per page and deduped by `id`; the loop terminates on `len(seen) >= totalCount` or an empty page.

### 3. Storage

Rows carry a `row_type` column:

- `row_type == "listing"` — one row per distinct listing at that snapshot.
- `row_type == "summary"` — one row per snapshot carrying the aggregate price and liquidity metrics.

Both share the same flat schema; fields not relevant to a row type are null. The scraper supports two sinks:

- `parquet` — append-only per-event parquet datasets under `data/`
- `duckdb` — a single local DuckDB database file

Each row is enriched with event metadata (`event_slug`, `event_name`, `venue_name`, `venue_city`, `event_start_utc`, `event_end_utc`) so the database sinks keep the same context that parquet previously encoded only in the filename.

### 4. Scheduler

`run_forever.py` runs `run_cycle()` in a loop. Each cycle:

1. Opens a fresh Playwright context (cookies fresh = WAF happy).
2. Refreshes the session manifest.
3. For every session with `end_utc > now`: warms the event page, fetches all listings, writes rows.
4. Closes the context and sleeps until the next hour boundary.

Per-cycle exceptions are logged and swallowed so a single bad request cannot crash the daemon.

---

## Liquidity & price schema

One `row_type == "summary"` row per snapshot per session:

| column              | meaning                                                          |
|---------------------|------------------------------------------------------------------|
| `snapshot_ts`       | UTC timestamp of the snapshot                                    |
| `event_id`          | StubHub event id                                                 |
| `listing_count`     | distinct active listings                                         |
| `total_quantity`    | sum of `availableTickets` across listings                        |
| `avg_price_usd`     | mean of `rawPrice` (fees included, buyer-facing)                 |
| `vwap_usd`          | quantity-weighted mean price                                     |
| `median_price_usd`  | median                                                           |
| `price_std_usd`     | population stdev                                                 |
| `min_price_usd`     | cheapest listing                                                 |
| `p10_price_usd`     | 10th percentile (linear-interpolated)                            |
| `max_price_usd`     | most expensive                                                   |
| `spread_proxy_usd`  | `p10_price_usd − min_price_usd` (bid/ask proxy for the cheap end)|

Per-listing rows additionally carry `section`, `row`, `ticket_class`, `quantity_available`, `raw_price_usd`, `face_value`, `deal_score`, `is_cheapest`, `created_dt`, etc. See `src/metrics.py` for the full list.

---

## Local usage

Requires Python 3.12+.

```bash
cd StubHubScraper
uv venv
uv pip install -r requirements.txt
uv run playwright install chromium

uv run python run_once.py        # one collection cycle (useful for smoke tests)
uv run python run_forever.py     # 24/7 loop, writes logs to logs/scraper.log
```

Parquet output lands in `data/` by default as one dataset directory per event. Inspect with:

```python
import pandas as pd
df = pd.read_parquet("data/event_158170204")
summary = df[df.row_type == "summary"].sort_values("snapshot_ts")
```

---

## Configuration

Runtime configuration is env-driven:

| env var | default | purpose |
|---|---|---|
| `STUBHUB_STORAGE_BACKEND` | `parquet` | one of `parquet`, `duckdb` |
| `STUBHUB_DATA_DIR` | `./data` | manifest, parquet, and default DuckDB file directory |
| `STUBHUB_LOG_DIR` | `./logs` | log directory for `run_forever.py` |
| `STUBHUB_DUCKDB_PATH` | `data/stubhub.duckdb` | DuckDB file path |
| `STUBHUB_DUCKDB_TABLE` | `stubhub_listings` | DuckDB table name |
| `STUBHUB_CATEGORY_URL` | Madrid Open category | event grid URL |
| `STUBHUB_SESSION_DURATION_HOURS` | `10` | inferred end time padding |
| `STUBHUB_PAGE_SIZE` | `10` | listing POST page size |
| `STUBHUB_MAX_PAGES` | `30` | hard page cap per event |
| `STUBHUB_REQUEST_PAUSE_SEC` | `0.5` | pause between listing POSTs |
| `STUBHUB_EVENT_PAUSE_SEC` | `2.0` | pause between events |
| `STUBHUB_CYCLE_INTERVAL_SEC` | `3600` | poll cadence |

Examples:

```bash
STUBHUB_STORAGE_BACKEND=duckdb \
STUBHUB_DUCKDB_PATH="$PWD/data/stubhub.duckdb" \
uv run python run_once.py
```

---

## Deployment

### Docker image

The repo now ships a Playwright-ready Dockerfile. Build and push it with:

```bash
docker build -t ghcr.io/kkhanna123/stubhub-scraper:latest .
docker push ghcr.io/kkhanna123/stubhub-scraper:latest
```

If you publish to a different registry, update `deploy/k8s/base/deployment.yaml`.

For a private GHCR image, authenticate first with a token that has `write:packages`:

```bash
export GHCR_OWNER=kkhanna123
export IMAGE_TAG=$(git rev-parse --short HEAD)
export IMAGE=ghcr.io/$GHCR_OWNER/stubhub-scraper:$IMAGE_TAG
export GHCR_PUSH_TOKEN=<github-token-with-write-packages>

echo "$GHCR_PUSH_TOKEN" | docker login ghcr.io -u "$GHCR_OWNER" --password-stdin
docker build -t "$IMAGE" .
docker push "$IMAGE"
```

### Kubernetes / boostrun

The Kubernetes manifests under `deploy/k8s/base/` deploy the scraper into namespace `stubhub-scraper` and persist a DuckDB file on a PVC at `/var/lib/stubhub-scraper/data/stubhub.duckdb`.

Render/apply them with:

```bash
kubectl kustomize deploy/k8s/base | kubectl apply -f -
```

If the image is private in GHCR, use the private overlay instead of the base manifest. It injects an `imagePullSecrets` entry and reads the image reference from a local `params.env` file so credentials and per-deploy image tags stay out of git.

1. Create the overlay params file:

    ```bash
    cp deploy/k8s/overlays/private-ghcr/params.env.example \
      deploy/k8s/overlays/private-ghcr/params.env
    ```

2. Edit `params.env` so `IMAGE=` points at the tag you pushed. You can keep `IMAGE_PULL_SECRET=ghcr-pull-secret` unless you want a different secret name.

3. Create or update the pull secret in Kubernetes with a token that has `read:packages`:

    ```bash
    export GHCR_PULL_TOKEN=<github-token-with-read-packages>
    kubectl -n stubhub-scraper create secret docker-registry ghcr-pull-secret \
      --docker-server=ghcr.io \
      --docker-username="$GHCR_OWNER" \
      --docker-password="$GHCR_PULL_TOKEN" \
      --dry-run=client -o yaml | kubectl apply -f -
    ```

4. Apply the overlay and wait for the rollout:

    ```bash
    kubectl apply -k deploy/k8s/overlays/private-ghcr
    kubectl -n stubhub-scraper scale deployment/stubhub-scraper --replicas=1
    kubectl -n stubhub-scraper rollout status deployment/stubhub-scraper
    ```

### VM / systemd deployment

Designed for a small Linux VM (Debian / Ubuntu) running as a systemd service.

1. Provision a VM with Python 3.12 and ≥ 1 GB free RAM (Chromium eats ~400 MB when running).

2. Clone and set up:

    ```bash
    sudo mkdir -p /opt/stubhubTicketScraper
    sudo chown $USER:$USER /opt/stubhubTicketScraper
    git clone <this-repo> /opt/stubhubTicketScraper
    cd /opt/stubhubTicketScraper
    uv venv
    uv pip install -r requirements.txt
    uv run playwright install --with-deps chromium
    ```

3. Install the systemd unit (edit `User` and `WorkingDirectory` to match your setup):

    ```bash
    sudo cp deploy/stubhub-scraper.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now stubhub-scraper
    ```

4. Tail logs / inspect output:

    ```bash
    journalctl -u stubhub-scraper -f            # live logs
    ls -la /opt/stubhubTicketScraper/data/      # parquet files
    ```

---

## Project layout

```
StubHubScraper/
├── Dockerfile
├── src/
│   ├── browser.py        # Playwright context manager + WAF-authenticated POST helper
│   ├── discovery.py      # category page → Event manifest (with persistence)
│   ├── listings.py       # paginated POST → all listings for one event
│   ├── metrics.py        # listing rows + summary-row builder
│   ├── storage.py        # parquet / DuckDB sinks
│   ├── scheduler.py      # hourly cycle runner + run_forever loop
│   └── config.py
├── scripts/              # throwaway reverse-engineering probes (kept for reference)
├── deploy/
│   ├── stubhub-scraper.service   # systemd unit
│   └── k8s/              # Kustomize base deployment
├── data/                 # parquet output, duckdb file, events_manifest.json
├── logs/                 # scraper.log (when run via run_forever.py)
├── run_once.py           # one-cycle entrypoint
├── run_forever.py        # 24/7 entrypoint
└── requirements.txt
```

---

## Known limitations

- **Category-page pagination is not implemented.** StubHub returns 6 upcoming sessions per load; newly-added sessions get picked up as they rotate into the top-6 window. Over the tournament this converges naturally, but brand-new sessions aren't seen instantly. If needed, this is a one-XHR fix — use the same browser-context POST pattern to hit the grid-pagination endpoint.

- **Session end time is inferred, not observed.** StubHub doesn't publish a session end time. `end_utc = start + SESSION_DURATION_HOURS` (default 10h) — generous enough to cover any normal day session, aggressive enough to stop polling shortly after the last match wraps up.

- **`rawPrice` is USD and includes fees.** That's what StubHub shows the buyer. `faceValue` (when non-null) is in the seller's local currency (`face_value_ccy`, usually EUR for Madrid).

- **Bot protection is adversarial.** Playwright + WAF cookies works today; if StubHub tightens fingerprinting you may need stealth plugins, residential proxies, or a switch to a paid listings API. The reverse-engineering scripts in `scripts/` are the fastest path to re-derive whatever changes.

- **Scraping ToS.** StubHub's Terms of Use prohibit automated access to the site. Use at your own risk; this is research/analytics code, not a production data source.
