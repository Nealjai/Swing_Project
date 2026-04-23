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

## How It Works: The Dual-Engine System

The screener's core logic is built around a dual-engine system that adapts to the current market environment. It first determines the market's health (the "regime") and then deploys the appropriate engine to find high-potential trading candidates.

### 1. Market Regime Determination

The screener's first and most crucial step is to classify the overall market regime. This determines which scanning engine will be used.

*   **Criteria**: The regime is determined by comparing the closing price of the **SPY (S&P 500 ETF)** to its **200-day Simple Moving Average (SMA)**.
    *   If `SPY Close > 200-day SMA`, the regime is **"Bull"**.
    *   If `SPY Close <= 200-day SMA`, the regime is **"Weak"**.

This simple but effective rule ensures that the screener is always aligned with the market's primary trend.

### 2. The Scanning Engines

Based on the detected regime, one of two specialized engines is activated.

#### a. The Bull Engine: Finding Market Leaders

*   **Objective**: To identify stocks in strong uptrends that are consolidating and poised for a breakout.
*   **Core Logic**:
    1.  **Uptrend Confirmation**: The stock must be trading above its own 200-day SMA.
    2.  **Pattern Recognition**: It looks for classic bullish patterns like the "Cup with Handle" (CWH) or "Volatility Contraction Pattern" (VCP).
    3.  **Scoring**:
        *   **Leadership Score**: Measures the stock's Relative Strength (RS) against the SPY. A high score means the stock is already outperforming the market.
        *   **Actionability Score**: Measures the quality of the setup. It rewards stocks that are close to a breakout point ("pivot"), show tight price consolidation, and have supportive volume patterns.

#### b. The Weak Engine: Spotting Rebound Opportunities

*   **Objective**: To identify fundamentally sound but oversold stocks that are due for a potential short-term rebound.
*   **Core Logic**:
    1.  **Oversold Condition**: The primary filter is a 14-day Relative Strength Index (RSI) below 30, indicating the stock is potentially oversold.
    2.  **Scoring**:
        *   **Leadership Score**: Even in a weak market, this score prioritizes stocks with better long-term trends and liquidity.
        *   **Actionability Score**: Measures the quality of the oversold setup by rewarding:
            *   **Extreme RSI**: Lower RSI values get a higher score.
            *   **Price Extension**: How far the stock has fallen below its recent trading range (Lower Bollinger Band).
            *   **Capitulation Volume**: A spike in volume that suggests seller exhaustion.

### 3. Scoring Formulas (High-Level)

The final score for each stock is a weighted average of its Leadership and Actionability scores.

*   **Final Score** = (Leadership Score * Leadership Weight) + (Actionability Score * Actionability Weight)

#### Bull Engine Formulas:

*   **Leadership Score** = `f(Relative Strength, Trend Strength)`
*   **Actionability Score** = `f(Proximity to Pivot, Price Volatility, Volume Contraction)`

#### Weak Engine Formulas:

*   **Leadership Score** = `f(Long-Term Trend, Liquidity)`
*   **Actionability Score** = `f(RSI Level, Price Extension from Bollinger Band, Volume Spike)`

### 4. The Result: A Filtered, Actionable Idea

A stock that appears in the screener results is not a "buy" signal. It is a high-potential, filtered idea that has passed a rigorous, data-driven set of rules based on the current market regime. The next step is for you to perform your own due diligence on the candidates that interest you.

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

## Backtesting module (local run)

Run backtests via [`scripts/run_backtest.py`](scripts/run_backtest.py:1):

```bash
python scripts/run_backtest.py
```

### CLI arguments (with defaults)
- `--engine` (default: `both`): `bull`, `weak`, or `both`
- `--symbol-mode` (default: `test`): `test` (curated 21-symbol set) or `full` (full universe from [`sp500.txt`](sp500.txt:1))
- `--start-date` (default: `2020-01-01`)
- `--end-date` (default: `2024-12-31`)

Portfolio simulator assumptions / controls:
- `--initial-capital` (default: `10000`)
- `--max-positions` (default: `5`)
- `--slippage-pct` (default: `0.0005` = 0.05% each side)
- `--commission-per-side` (default: `0.32` dollars)
- `--monthly-dd-limit-pct` (default: `6.0`)
- `--monthly-risk-per-trade-pct` (default: `1.0`)
- `--risk-free-rate-annual` (default: `0.0`) for Sharpe/Sortino
- `--trading-days-per-year` (default: `252`) for Sharpe/Sortino annualization

Example explicit run matching defaults:

```bash
python scripts/run_backtest.py --engine both --symbol-mode test --start-date 2020-01-01 --end-date 2024-12-31
```

### Backtest outputs
- Committed summary artifact: [`docs/data/backtest_summary.json`](docs/data/backtest_summary.json:1)
- Local-only trade logs: `data/backtests/trades_YYYYMMDD_HHMM.csv`
  - Generated by [`write_trade_log()`](src/screener/backtest/output.py:11)
  - Kept out of git by [`data/backtests/`](.gitignore:5)

[`docs/data/backtest_summary.json`](docs/data/backtest_summary.json:1) now includes:
- `portfolio.assumptions`
- `portfolio.metrics` (Total Return, CAGR, Max Drawdown, Exposure, Months Halted, Sharpe, Sortino, etc.)
- `portfolio.curve` (daily `dates`, `equity`, `drawdown_pct`)
- `portfolio.monthly_returns`

### Backtest integrity rules (implementation summary)
- Entry timing: signal on day *t*, entry at next session open (*t+1*) via [`_simulate_symbol()`](src/screener/backtest/engine.py:58)
- Regime gating: bull/weak signals are only valid when benchmark regime for that date matches via [`_regime_state_series()`](src/screener/backtest/engine.py:50)
- Warmup: first 200 bars are excluded before simulation via [`BacktestConfig.warmup_bars`](src/screener/backtest/engine.py:23)
- Price semantics: signal generation uses adjusted-close (`signal_close`) while realized P&L uses raw close/open execution fields (`Open`/`Close`) in [`_simulate_symbol()`](src/screener/backtest/engine.py:58)

## Dashboard Backtesting tab
- The **Backtesting** tab in [`docs/index.html`](docs/index.html:124) lazy-loads [`docs/data/backtest_summary.json`](docs/data/backtest_summary.json:1) on first click via [`loadBacktestSummaryIfNeeded()`](docs/app.js:923).
- The equity chart is now a **real portfolio equity curve** from [`simulate_portfolio()`](src/screener/backtest/portfolio.py:158), not an expectancy-derived synthetic curve.
- The tab includes:
  - engine trade-stat cards,
  - portfolio metric cards (including Sharpe/Sortino),
  - portfolio equity + drawdown chart,
  - monthly returns table,
  - annual trade-stats breakdown table.
- If no summary file is present (or it cannot be fetched), the empty-state/error message means local backtests have not been generated yet for this repo snapshot (or the page is not being served correctly over HTTP).
- Generate/update summary first with [`scripts/run_backtest.py`](scripts/run_backtest.py:1), then refresh the dashboard.

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
