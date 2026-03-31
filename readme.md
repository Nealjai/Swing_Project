# US Market Regime Dual-Engine Stock Screener

## Overview
A V1 stock screening and research dashboard for U.S. equities. A Python pipeline fetches daily end-of-day data, detects the current market regime using SPY versus the 200-day SMA, runs the appropriate screening engine, and exports static JSON and CSV files. A static HTML/CSS/JS frontend reads the latest JSON and renders a ranked candidates dashboard.

## Confirmed V1 defaults
- Universe: tickers from [`sp500.txt`](sp500.txt:1)
- Regime benchmark: SPY
- Regime rule: SPY close vs SMA200
- Data: yfinance daily EOD
- Outputs: JSON primary and CSV secondary
- Cadence: automated daily GitHub Actions run + manual trigger + local manual run
- Scope: screening and research only, no execution

## How it works
1. Load universe.
2. Fetch daily EOD price data.
3. Compute indicators.
4. Detect regime.
5. Screen and rank candidates.
6. Export JSON and CSV.
7. Static dashboard loads JSON and displays results.

## Local install and run

### 1) Create and activate a Python virtual environment
Windows (`cmd.exe`):
```bat
python -m venv .venv
.venv\Scripts\activate
```

macOS/Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2) Install dependencies
```bash
pip install -r requirements.txt
```
Dependencies are defined in [`requirements.txt`](requirements.txt:1).

### 3) Run the daily pipeline locally
```bash
python scripts/run_daily.py
```
This regenerates static artifacts, including [`docs/data/latest.json`](docs/data/latest.json:1) and [`docs/data/latest.csv`](docs/data/latest.csv:1).

The JSON now also includes:
- Candidate `risk` (SL/TP based on ATR14 and bb_lower/high_20d)
- Candidate `fundamentals` (ROE, P/E, Revenue Growth QoQ/YoY when available)
- `charts` (1Y chart series for top 20 candidates + SPY benchmark)

## Local web UI testing

### Option A (no installs): run a simple local server
Serve [`docs/`](docs/:1) as a static site:

```bash
python -m http.server 5500 --directory docs
```

Then open:
- `http://localhost:5500/`

This is preferred over opening [`docs/index.html`](docs/index.html:1) directly because `fetch()` for local JSON works reliably over HTTP.

UI-only changes:
- Save changes under [`docs/`](docs/:1)
- Refresh browser

Logic/data changes:
- Re-run [`scripts/run_daily.py`](scripts/run_daily.py:1) to regenerate [`docs/data/latest.json`](docs/data/latest.json:1)
- Refresh browser

### Option B (optional): VS Code Live Server (auto-reload)
If you want **save → browser auto-refresh**:
1. Install the **Live Server** VS Code extension
2. Right-click [`docs/index.html`](docs/index.html:1) → **Open with Live Server**

Notes:
- Live Server only auto-reloads when files change.
- It does **not** automatically re-run Python; for logic changes you still run [`scripts/run_daily.py`](scripts/run_daily.py:1), then the browser will reload once the JSON changes.

## GitHub Pages deployment (serve from `/docs`)
1. Open repository **Settings** → **Pages**.
2. Under **Build and deployment**, choose **Deploy from a branch**.
3. Select your default branch and folder **`/docs`**, then save.
4. Your site will publish from files in [`docs/`](docs/:1), including dashboard assets and generated data artifacts.

## Automated data regeneration and publish
- Workflow file: [`.github/workflows/daily_screener.yml`](.github/workflows/daily_screener.yml:1)
- Triggers:
  - Daily schedule (UTC cron tuned for U.S. EOD availability)
  - Manual run via `workflow_dispatch`
- Pipeline steps:
  1. Checkout repository
  2. Setup Python 3.11
  3. Install dependencies from [`requirements.txt`](requirements.txt:1)
  4. Run [`scripts/run_daily.py`](scripts/run_daily.py:1)
  5. Commit and push updated artifacts in [`docs/data/`](docs/data/:1), only when content changed
- Current committed publish targets include:
  - [`docs/data/latest.json`](docs/data/latest.json:1)
  - [`docs/data/latest.csv`](docs/data/latest.csv:1)

## Manual workflow trigger
1. Open the **Actions** tab in GitHub.
2. Select **Daily Screener Publish**.
3. Click **Run workflow** on the default branch.
4. After completion, refreshed artifacts are available under [`docs/data/`](docs/data/:1).

## Cache behavior
- [`data/cache/`](data/cache/:1) is not committed and is ignored by git.
- Workflow commit step stages only static publish artifacts in [`docs/data/`](docs/data/:1).

## Documentation
- Spec: [`spec.md`](spec.md:1)
- Implementation checklist: [`todolist.md`](todolist.md:1)
- Progress log: [`report.md`](report.md:1)
- Lessons and preferences: [`lessons.md`](lessons.md:1)
