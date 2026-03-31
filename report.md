# Project Report

## 2026-03-30

### Dashboard + export contract expansion
- Expanded the static dashboard UI under [`docs/`](docs/:1):
  - Tabbed layout: Screener Results + Background + Historical (placeholder)
  - Screener Results: left candidates table and right details panel with chart
  - Chart rendering via Chart.js, with per-series visibility toggles
  - Background tab includes a SPY benchmark chart
- Expanded the JSON contract in [`docs/data/latest.json`](docs/data/latest.json:1):
  - Candidate `risk` fields (ATR-based SL/TP derived from bb_lower/high_20d)
  - Candidate `fundamentals` fields (ROE, P/E, revenue growth QoQ/YoY when available)
  - `charts` payload (1Y series for top 20 candidates + SPY benchmark)

### Local dev-loop documented
- Documented the recommended local preview loop in [`readme.md`](readme.md:1):
  - Serve the static site from [`docs/`](docs/:1) via `python -m http.server`
  - Optional Live Server for auto-reload (still requires running [`scripts/run_daily.py`](scripts/run_daily.py:1) for logic/data changes)

## 2026-03-29

### Planning documentation
- Created initial planning docs per project context:
  - [`spec.md`](spec.md:1)
  - [`todolist.md`](todolist.md:1)
  - [`readme.md`](readme.md:1)
  - [`report.md`](report.md:1)
  - [`lessons.md`](lessons.md:1)

### V1 milestone delivered
- Delivered V1 screener pipeline and static dashboard flow for screening/research usage.
- Implemented runtime path that generates latest artifacts under [`docs/data/`](docs/data/:1).
- Confirmed latest contract artifacts:
  - [`docs/data/latest.json`](docs/data/latest.json:1)
  - [`docs/data/latest.csv`](docs/data/latest.csv:1)

### Automation milestone delivered (GitHub Actions)
- Added scheduled + manual automation at [`.github/workflows/daily_screener.yml`](.github/workflows/daily_screener.yml:1).
- Workflow regenerates static artifacts by running [`scripts/run_daily.py`](scripts/run_daily.py:1) with dependencies from [`requirements.txt`](requirements.txt:1).
- Workflow commits only changed publish outputs under [`docs/data/`](docs/data/:1), avoiding no-op commit noise.
- Added ignore rule for [`data/cache/`](data/cache/:1) via [`.gitignore`](.gitignore:1) so local cache files remain untracked.

### Confirmed V1 defaults encoded
- Universe: [`sp500.txt`](sp500.txt:1)
- Regime benchmark: SPY
- Regime rule: close vs SMA200
- Data: yfinance daily EOD
- Outputs: JSON primary and CSV secondary
- Cadence: local manual run + automated daily workflow + manual workflow trigger
- Scope: screening and research only
