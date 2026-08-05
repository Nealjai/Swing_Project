# Project Report

## 2026-06-27

### Execution-contract reliability hardening (TP legacy cleanup)
- Removed legacy TP exit branches from [`simulate_portfolio()`](src/screener/backtest/portfolio.py:161):
  - deleted `tp_gap_open`/`tp_intraday`-driven closure logic
  - preserved hard stop-loss + planned time-stop behavior
  - renamed partial activation fill reason from `activation_half_take_profit` to `activation_partial_exit_half`.
- Hardened daily risk payload contract in [`_attach_risk_fields()`](scripts/run_daily.py:180):
  - added `risk.schema_version = "2.1"`
  - kept `activation_level` as canonical activation field
  - retained `take_profit` as a documented deprecated compatibility alias.
- Updated screener UI contract wording to remove TP semantics:
  - table/detail rendering now reads strict `risk.activation_level` in [`docs/app.js`](docs/app.js:640)
  - labels changed from `Activation (TP1)` to `Activation` in [`docs/app.js`](docs/app.js:813) and [`docs/index.html`](docs/index.html:177).
- Added execution-contract regression tests in [`tests/test_portfolio_execution_contract.py`](tests/test_portfolio_execution_contract.py:1):
  - verifies portfolio no longer emits TP-prefixed exit reasons
  - verifies activation partial-exit fill reason uses contract-safe naming.

## 2026-06-24

### Backtesting rebuild milestone (core + active scenarios)
- Implemented robust eligibility + reproducible sampling in [`run_backtest()`](src/screener/backtest/engine.py:529):
  - added config controls for sample size/seed and full-window requirement.
  - records `eligible_symbols`, `sampled_symbols`, `sample_target`, `sample_seed`, plus `skip_reason_counts` diagnostics.
- Updated CLI defaults/controls in [`parse_args()`](scripts/run_backtest.py:74):
  - `--max-positions` default set to 8.
  - added `--sample-size`, `--sample-seed`, `--allow-partial-history-window`.
- Upgraded exit realism in [`simulate_portfolio()`](src/screener/backtest/portfolio.py:161):
  - gap-open SL/TP checks.
  - intraday OHLC SL/TP checks.
  - conservative same-bar conflict handling (`SL` priority when both touch intraday).
- Extended portfolio metrics in [`simulate_portfolio()`](src/screener/backtest/portfolio.py:736):
  - added `calmar`, `win_rate`, `profit_factor`, `expectancy_pct`, `avg_hold_days`.
- Made yearly trade summaries dynamic in [`summarize_trades()`](src/screener/backtest/stats.py:90) so years derive from data instead of fixed 2020..2024.
- Updated Backtesting active compare/diagnostics UI in [`BACKTEST_COMPARE_METRICS`](docs/app.js:1665) and [`renderBacktestActiveView()`](docs/app.js:2058) to surface new KPIs and sampling diagnostics.
- Added fixed active scenario export wiring in [`main()`](scripts/run_backtest.py:424):
  - writes `docs/data/backtest_active_10k.json` when capital=10000 and max_positions=8.
  - writes `docs/data/backtest_active_30k.json` when capital=30000 and max_positions=8.

### Validation
- Syntax compile passed:
  - `python3 -m py_compile src/screener/backtest/engine.py src/screener/backtest/portfolio.py src/screener/backtest/stats.py scripts/run_backtest.py`
- Smoke runs completed successfully:
  - 10k/8 run wrote [`docs/data/backtest_active_10k.json`](docs/data/backtest_active_10k.json).
  - 30k/8 run wrote [`docs/data/backtest_active_30k.json`](docs/data/backtest_active_30k.json).

## 2026-05-31

### Policy B+ regime-aware bull pipeline + tracker enforcement
- Implemented Policy B+ in [`bull_candidates()`](src/screener/engines/bull.py:758): bull engine now accepts `regime_label` and emits `intent` as `trade` or `watchlist` instead of blindly treating all bull outputs as trade-ready.
- Added absolute/excess RS features in [`_compute_rs_block()`](src/screener/engines/bull.py:189):
  - `stock_return_20d/60d/90d`
  - `excess_return_20d/60d/90d` (stock minus SPY)
  - retained ratio-style RS returns with safer near-zero denominator guard.
- Updated bull scoring inputs to blend relative + absolute strength so bear-tape “slower losers” are surfaced as watchlist leaders without being promoted to trade intent by default.
- Added regime policy fields to bull outputs in [`bull_candidates()`](src/screener/engines/bull.py:1037):
  - `regime_label`, `intent`, `regime_policy`, `regime_reason`
  - plus debug gates `bear_watchlist_gate` and `bear_trade_gate`.
- Updated daily orchestration in [`main()`](scripts/run_daily.py:273):
  - compute market condition once via [`get_market_condition()`](src/screener/market_condition.py:198)
  - pass `regime_label` into bull engine
  - run bull + weak engines together and rank a combined list
  - diagnostics now include per-engine raw candidate counts.
- Enforced tracker gating for Policy B+ in [`_is_tracker_eligible()`](src/screener/tracker.py:122): watchlist-intent bull candidates are excluded from tracker; only trade-intent bull candidates can be tracked.
- Persisted regime context in tracker records via [`_new_tracker_record()`](src/screener/tracker.py:261): now stores `regime_label`, `intent`, `regime_reason`.
- Validation completed:
  - `python3 -m py_compile src/screener/engines/bull.py scripts/run_daily.py src/screener/tracker.py`
  - `python3 -m unittest tests/test_scoring.py tests/test_bull_policy_b_plus.py`

## 2026-04-25

### Tracker tab + 10-trading-day post-discovery tracker (additive, deployment-safe)
- Added dedicated tracker pipeline in [`update_tracker_file()`](src/screener/tracker.py:288) with persistent storage at [`docs/data/tracker.json`](docs/data/tracker.json).
- Tracker inclusion rule implemented exactly as approved:
  - bull engine only
  - top 10 rank only
  - both tags required (🏆 via `leadership_score >= 0.90`, ⚡ via `actionability_score >= 0.58`)
  - auto-drop after 10 trading days
  - symbol can be re-added after drop on a new qualified discovery
- Tracker schema implemented in persisted records includes approved fields:
  - `symbol`, `capture_date_utc`, `capture_close`, `current_close`, `return_since_capture_pct`, `days_tracked_trading`, `expiry_date_utc`, `status`, `rank_at_capture`, `score_at_capture`, `distance_to_sma20_pct`, `rsi14`, `volume_buzz_ratio`, `last_updated_utc`.
- Integrated tracker update into daily runtime via [`main()`](scripts/run_daily.py:203), without changing existing screener artifact contract ([`docs/data/latest.json`](docs/data/latest.json:1) remains unchanged).
- Added a new Tracker UI tab in [`docs/index.html`](docs/index.html:29) and rendering logic in [`renderTracker()`](docs/app.js:2891), with table/summary cards and status chips.
- Added tracker-specific styling in [`docs/styles.css`](docs/styles.css:379).
- Validation:
  - Python syntax compile for modified backend modules
  - Daily run generated tracker artifact with expected rule metadata and counts.

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
- Universe: [`universe.txt`](universe.txt:1)
- Regime benchmark: SPY
- Regime rule: close vs SMA200
- Data: yfinance daily EOD
- Outputs: JSON primary and CSV secondary
- Cadence: local manual run + automated daily workflow + manual workflow trigger
- Scope: screening and research only
