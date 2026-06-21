# US Market Regime Playbook-First Stock Screener

Static, research-focused U.S. equity screener with:
- regime-aware candidate generation,
- playbook-first policy routing,
- cash-first execution logic,
- risk-based position sizing for small accounts (default $10,000),
- tracker lifecycle monitoring,
- market condition diagnostics,
- portfolio-style backtesting,
- and a GitHub Pages dashboard served from `docs/`.

## What the project does (current state)

This project runs a Python pipeline that:
1. Loads a U.S. stock universe (default: `universe.txt`).
2. Fetches EOD OHLCV/fundamental context from Yahoo Finance (`yfinance`).
3. Retrieves quote metrics with reliability-first split sources:
   - `market_cap`: `Ticker.fast_info.market_cap` (cached, with last-resort fallback paths).
   - `beta_1y`: computed from daily **Adj Close** returns vs benchmark (`SPY` by default), cached and reused.
4. Detects market regime from SPY market-condition signals.
5. Runs both engines (`bull` + `weak`) to create raw candidates.
6. Routes candidates through a playbook-first policy layer:
   - infer playbook,
   - apply absolute quality gates,
   - apply regime permissioning,
   - assign `intent` (`trade` / `watchlist`).
7. Enforces cash-first behavior:
   - if no qualified trade remains, output `trade_allowed=false` with `cash_reason`.
8. Computes risk fields (stop, activation, and max shares using account constraints).
9. Exports static artifacts (`JSON` + `CSV`) for the dashboard.
10. Updates tracker and market condition artifacts.
11. Exports per-symbol 3Y daily files for dashboard charting.

The frontend (`docs/index.html` + `docs/app.js`) reads those files directly (no backend server).

---

## Core modules

- `scripts/run_daily.py`: daily screener pipeline + artifact generation.
- `scripts/run_backtest.py`: backtest runner + portfolio simulation + run history artifacts.
- `src/screener/engines/bull.py`: bull-regime candidate logic.
- `src/screener/engines/weak.py`: weak-regime candidate logic.
- `src/screener/engines/playbook.py`: playbook routing, absolute gates, regime permissioning, cash policy.
- `src/screener/engines/scoring.py`: robust normalization/scoring helpers.
- `src/screener/tracker.py`: tracker lifecycle engine and hybrid shortlist admission rules.
- `src/screener/market_condition.py`: market condition metrics and chart payload.
- `src/screener/backtest/*`: backtest engine, portfolio simulator, stats, output writers.
- `src/screener/quote_metrics.py`: reliability-first market-cap and beta retrieval/caching.
- `docs/*`: static dashboard UI.

---

## Screening logic summary

### Regime detection
- Benchmark: `SPY`
- Market condition classifier labels `Bull`, `Choppy`, or `Bear`.

### Candidate generation + playbook policy
- Both engines run daily and emit raw candidates.
- Playbook policy layer then:
  - infers/normalizes playbook IDs,
  - applies absolute quality gates (price/liquidity/volatility/score constraints),
  - applies regime-permitted execution logic,
  - emits final candidates with intent.

### Cash-first behavior
- No forced trades.
- If zero qualified trade-intent candidates survive policy gates:
  - `trade_allowed=false`
  - `cash_reason=<explicit reason>`
  - banner/UI shows `HOLD CASH`.

### Normalized scoring model
Scoring uses robust cross-sectional normalization (median/MAD + sigmoid) and outputs normalized sub-scores.

- Bull:
  - leadership = RS + trend blend
  - actionability = breakout + compression + volume + stage blend
  - final score = weighted leadership/actionability blend (scaled to 0-100)

- Weak:
  - leadership = trend + liquidity blend
  - actionability = reversal + extension + capitulation blend
  - final score = weighted leadership/actionability blend (scaled to 0-100)

### Candidate tags
Dashboard tags are threshold-based:
- 🏆 leadership when `leadership_score >= 0.90`
- ⚡ actionable when `actionability_score >= 0.58`
- 👀 watchlist when `0.50 <= actionability_score < 0.58`

### Tracker admission (hybrid rule)
Tracker is an execution shortlist, not a broad watchlist.

Required:
- `intent == trade`
- `rank <= 10`
- `risk.position_sizing.max_shares > 0`

Quality route:
- strict route (🏆 + ⚡) OR
- relaxed playbook route for selected playbooks.

### Quote-metrics reliability policy
- `Ticker.info` is **not** the primary dependency for `market_cap` and `beta_1y`.
- `market_cap` primary source: `Ticker.fast_info.market_cap`.
- `beta_1y` primary source: computed 1-year beta from daily **Adj Close** returns:
  - `beta_1y = cov(stock_returns, benchmark_returns) / var(benchmark_returns)`
  - benchmark defaults to `SPY`
  - 252-trading-day window with minimum-observation guardrail.
- Cached quote metrics are reused to reduce repeated API pressure and improve run stability.
- `Ticker.info` remains only as last-resort fallback for compatibility.

---

## Dashboard features (`docs/`)

Tabs currently available:
- **Screener Result**
  - List View + Chart View
  - cash-first banner (`TRADE MODE` / `HOLD CASH`) with qualified trade count and reason
  - ranked table includes Playbook, Intent, Max Shares, Stop Loss, Activation
  - candidate details, fundamentals, 3Y chart
  - indicator toggles (SMA10/20/50/100/200, volume)
- **Market Condition**
  - market regime/SPY/VIX/DD/FTD cards
  - SPY condition chart
- **How It Works**
  - high-level strategy flow
  - playbook-first + cash-first explanation
  - expandable rule details section with key thresholds
- **Backtesting**
  - fixed active scenario switch: `10k` and `30k`
  - KPI cards, equity/drawdown chart, strategy-vs-SPY chart
  - monthly and annual breakdown tables
  - methodology + diagnostics sections
- **Tracker**
  - 2-week lifecycle tracker for hybrid-qualified trade-intent discoveries
  - active/inactive states, lifecycle tags, per-symbol chart with controls

---

## Output artifacts

### Daily screener outputs
Generated by `python scripts/run_daily.py`:
- `docs/data/latest.json`
- `docs/data/latest.csv`
- `docs/data/tracker.json`
- `docs/data/market_condition.json`
- `docs/data/daily/<SYMBOL>.json` (3Y OHLCV series per symbol, including SPY)

### Backtest outputs
Generated by `python scripts/run_backtest.py`:
- `docs/data/backtest_summary.json` (latest summary for dashboard consumption; appears after a local run)
- `docs/data/backtest_runs/index.json` (run registry)
- `docs/data/backtest_runs/backtest_summary_<run_id>.json`
- `docs/data/backtest_runs/run_config_<run_id>.json`
- `docs/data/backtest_runs/symbols_<run_id>.json`
- `docs/data/backtest_runs/candidates_<run_id>.csv`
- `data/backtests/trades_<timestamp>.csv` (local trade log, gitignored)

Backtesting tab also reads fixed active datasets:
- `docs/data/backtest_active_10k.json`
- `docs/data/backtest_active_30k.json`

---

## Local setup

### 1) Create virtual environment
macOS/Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows (cmd):
```bat
python -m venv .venv
.venv\Scripts\activate
```

### 2) Install dependencies
Runtime only:
```bash
pip install -r requirements.txt
```

Runtime + test tooling:
```bash
pip install -r requirements-dev.txt
```

`requirements.txt` is kept minimal for production/runtime execution. `requirements-dev.txt` layers on dev/test tools (e.g., `pytest`).

---

## Run commands

### Daily screener pipeline
```bash
python scripts/run_daily.py
```

### Backtest pipeline
```bash
python scripts/run_backtest.py
```

### Unit tests
Run from `Swing_Project/` root:
```bash
python3 -m pytest -q
```

Example backtest run:
```bash
python scripts/run_backtest.py --engine both --symbol-mode full --years 10
```

### Scalability knobs for large universes (e.g., 3000+ symbols)
You can tune these in `src/screener/config.py`:
- `download_batch_size`: yfinance batch width for OHLCV downloads.
- `yfinance_max_retries`: retry count for transient yfinance failures.
- `cache_max_age_days`: acceptable age for cached OHLCV files.
- `ticker_info_max_workers`: concurrent workers for ticker info fetches.
- `ticker_info_cache_max_age_days`: cache TTL for ticker info JSON files.

Operational recommendation for 3000+ symbols:
- Keep `market_aware_refresh` enabled for daily runs.
- Use incremental cache refresh (already built into `fetch_prices`).
- Avoid forcing full refresh except when changing lookback assumptions.

---

## Local dashboard preview

Serve static files over HTTP (recommended):
```bash
python -m http.server 5500 --directory docs
```

Open: `http://localhost:5500/`

Do not open `docs/index.html` directly with `file://` if you expect `fetch()` data loading to work reliably.

---

## GitHub Actions automation

Workflow: `.github/workflows/daily_screener.yml`

Current workflow behavior:
- scheduled + manual trigger
- installs dependencies
- runs `python scripts/run_daily.py`
- commits/pushes updated static artifacts when changed

Currently staged in workflow commit step:
- `docs/data/latest.json`
- `docs/data/latest.csv`
- `docs/data/tracker.json`
- `docs/data/market_condition.json`
- `docs/data/daily/`

### Local Git workflow (code-only commits)

This repository is configured so generated dashboard artifacts are workflow-owned.

Ignored locally via `.gitignore`:
- `docs/data/*.json`
- `docs/data/*.csv`
- `docs/data/daily/`

Recommended cycle before every push to `main`:
```bash
git checkout main
git pull --rebase origin main
git status
# edit code/docs only
git add <code_or_docs_files>
git commit -m "<message>"
git push origin main
```

Local safety guard:
- Pre-commit hook at `.githooks/pre-commit` blocks accidental commits of `docs/data/*` artifacts.
- If needed on a fresh clone, enable it once:

```bash
chmod +x .githooks/pre-commit
git config core.hooksPath .githooks
```

---

## Important notes

- Research/screening tool only; no brokerage integration or auto-execution.
- Results are candidate ideas, not buy/sell advice.
- Enforce your own risk management and due diligence.

---

## Project docs

- Spec: `spec.md`
- Task list: `todolist.md`
- Progress log: `report.md`
- Lessons learned: `lessons.md`
