# Project Report

## 2026-04-18

### Normalized scoring refactor for bull/weak engines
- Added shared robust normalization utilities in [`robust_unit_score()`](src/screener/engines/scoring.py:37) with median/MAD + sigmoid mapping to `[0,1]`, including neutral fallback behavior for missing values/small populations.
- Refactored [`bull_candidates()`](src/screener/engines/bull.py:707) to remove RS/pattern hard gates and move to dual-axis soft scoring:
  - `leadership_score` (RS + trend)
  - `actionability_score` (breakout proximity + compression + volume + stage)
  - final normalized `score` as the production ranking field.
- Refactored [`weak_candidates()`](src/screener/engines/weak.py:8) into the same model family with reversal/extension/capitulation actionability and trend/liquidity leadership.
- Implemented user-facing setup labels (`Both`, `Actionable Breakout`, `Leadership`, `Watchlist`) as `setup_tag` in both engines.
- Preserved old score formulas only in debug payload (`debug_metrics.legacy_score`) to support side-by-side validation.

### Liquidity gate + pipeline alignment
- Added `min_avg_dollar_volume_20d` setting in [`Settings`](src/screener/config.py:9) and passed it in runtime engine calls from [`main()`](scripts/run_daily.py:203).
- Added scanner export propagation in [`export_outputs()`](src/screener/export.py:30) so `scanner_settings` now includes `min_avg_dollar_volume_20d`.
- Updated backtest eligibility in both [`_simulate_symbol()`](src/screener/backtest/engine.py:60) and [`_generate_symbol_candidates()`](src/screener/backtest/engine.py:236) to enforce `avg_dollar_volume_20d >= min_avg_dollar_volume_20d`.

### Validation completed
- Added unit tests in [`tests/test_scoring.py`](tests/test_scoring.py:1) for:
  - missing value fallback
  - small population fallback
  - NaN/Inf handling in population
  - zero-MAD edge behavior
  - invert direction correctness
  - output bound checks
- Verified syntax compilation across modified modules via `python3 -m py_compile`.
- Ran smoke backtest via [`scripts/run_backtest.py`](scripts/run_backtest.py:141) for `--engine both --symbol-mode test --start-date 2023-01-01 --end-date 2024-12-31` (completed successfully).

## 2026-04-06

### Portfolio simulator (Option C) integrated into backtesting
- Implemented signal-level candidate generation via [`_generate_symbol_candidates()`](src/screener/backtest/engine.py:236) and extended [`BacktestResult`](src/screener/backtest/engine.py:27) to include `candidates` and `prices` for portfolio simulation inputs.
- Added portfolio simulator module via [`simulate_portfolio()`](src/screener/backtest/portfolio.py:158) with locked assumptions:
  - initial capital 10,000
  - max 5 concurrent positions
  - equal-weight sizing + integer shares (floor)
  - no leverage
  - slippage 0.05% each side
  - commission $0.32 each side
  - monthly drawdown guard: halt new entries below -6% from month-start equity
  - risk cap: 1% per trade vs month-start equity
  - same-day entry ranking by `signal_avg_dollar_volume_20d` descending
- Added portfolio risk/performance metrics including Sharpe and Sortino via [`_compute_sharpe_sortino()`](src/screener/backtest/portfolio.py:106).
- Added monthly return series via [`_build_monthly_returns()`](src/screener/backtest/portfolio.py:135).
- Extended summary schema via [`build_summary_payload()`](src/screener/backtest/output.py:51) and pipeline wiring in [`main()`](scripts/run_backtest.py:141) to emit `portfolio.assumptions`, `portfolio.metrics`, `portfolio.curve`, and `portfolio.monthly_returns`.
- Updated dashboard rendering:
  - portfolio metric cards via [`renderBacktestPortfolioCards()`](docs/app.js:688)
  - portfolio equity + drawdown chart via [`renderBacktestEquityChart()`](docs/app.js:727)
  - monthly return table via [`renderBacktestMonthlyTable()`](docs/app.js:836)
  - history tab structure in [`docs/index.html`](docs/index.html:124)
  - styling in [`docs/styles.css`](docs/styles.css:388)
- Regenerated [`docs/data/backtest_summary.json`](docs/data/backtest_summary.json:1) using [`scripts/run_backtest.py`](scripts/run_backtest.py:1) with default test universe.

### Backtesting module + dashboard tab documentation refresh
- Updated [`readme.md`](readme.md:1) to document local backtest execution via [`scripts/run_backtest.py`](scripts/run_backtest.py:1), including CLI defaults for engine, symbol mode, and date range.
- Documented backtest artifact contract:
  - committed summary: [`docs/data/backtest_summary.json`](docs/data/backtest_summary.json:1)
  - local-only trade logs: `data/backtests/trades_YYYYMMDD_HHMM.csv` (gitignored via [`.gitignore`](.gitignore:1))
- Added backtest integrity notes to docs (next-open entry, regime filter, 200-bar warmup, adjusted-close signal evaluation vs raw-price P&L semantics).
- Added Backtesting tab usage notes, including lazy-load behavior and what the empty/error state means when summary data is missing.

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
