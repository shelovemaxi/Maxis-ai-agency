# Signal Wire

Signal Wire is a local, no-signup market intelligence dashboard for macro, equities, crypto, commodities, geopolitics, and natural events. It uses free public RSS/Atom feeds plus GDELT DOC and USGS earthquake data. It does **not** scrape Twitter/X and does not use paid World Monitor APIs.

## Quick start

### Linux/macOS
```bash
cd signal-wire
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
./run.sh
```

### Windows PowerShell
```powershell
cd signal-wire
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\run.bat
```

Open http://127.0.0.1:5050. Flask is optional: without it, the app starts a standard-library server with API access and a minimal landing page.

## GitHub Pages deployment

The `docs/` folder is a static, GitHub Pages-compatible version. It reads the checked-in `docs/data.json` snapshot, so it works without a server or API key. The included workflow at `.github/workflows/update-signal-wire.yml` refreshes that snapshot every 15 minutes using public feeds.

After pushing this folder to a repository:

1. Open **Settings → Pages**.
2. Choose **Deploy from a branch**.
3. Select `main` and the `/docs` folder, then save.
4. In **Actions**, run **Refresh Signal Wire data** once manually if you want an immediate update.

The project URL will normally be `https://USERNAME.github.io/REPOSITORY/signal-wire/`.

## Endpoints
- `/` dashboard
- `/api/items` current cached signals
- `POST /api/refresh` force a refresh (asynchronous)
- `/api/status` source health, cache status, and errors
- `/health` liveness JSON

## How it works
Feeds and queries are configured near the top of `app.py`. Requests use a timeout and descriptive User-Agent. XML is parsed with the Python standard library. Each item receives transparent phrase-based weights for rate decisions, inflation, jobs, recession, sanctions, tariffs, conflict, OPEC, energy, disruptions, failures, hacks, ETFs, liquidations, and other signals; noise phrases reduce scores. Percentage moves contribute a capped boost. Scores are 0–100: High (60+), Medium (30–59), Low (<30). Normalized duplicate titles are collapsed and items reported by multiple distinct domains get a small corroboration boost. The UI shows matched reasons, source, timestamp, and original link.

The cache is written atomically to `data/cache.json`; if a refresh fails, the last successful data remains available. Automatic refresh is limited to every 15 minutes, while the dashboard polls status periodically. Threshold and filter preferences are stored only in browser localStorage.

## Limitations, privacy, and safety
Feeds can be delayed, blocked, malformed, rate-limited, or unavailable. Some publishers change RSS URLs or restrict access. GDELT results are broad and may include noisy reporting. Scores are rule-based prioritization, not predictions, fact verification, or investment advice. Always open the original source and independently verify important information. No credentials or user data are collected; this is intended for local use. Do not make trading decisions solely from this dashboard.

## Troubleshooting
- Check `/api/status` for per-source errors.
- If port 5050 is busy, run `PORT=5051 python3 app.py` (PowerShell: `$env:PORT=5051; py app.py`).
- A firewall, proxy, DNS issue, or publisher rate limit can cause feed failures; cached data will still display after the first successful refresh.
- If Flask installation is unavailable, the standard-library fallback still serves `/health` and JSON endpoints; install requirements for the full UI.
