# Portfolio simulator + real equity curve (Option C)

This replaces the current annual-aggregate curve built in [`buildEquitySeriesFromAnnualExpectancy()`](../docs/app.js:683) with a portfolio-defined, daily mark-to-market equity curve and risk metrics.

## Goals

- Produce a *real* portfolio equity curve from backtest signals/trades.
- Add portfolio metrics: total return %, CAGR, max drawdown, monthly DD halt count, exposure.
- Add risk-adjusted metrics from the daily equity curve: **Sharpe** and **Sortino**.
- Add a **monthly returns** table for the dashboard.
- Keep existing per-trade stats (win rate, avg win/loss, expectancy, profit factor) as a separate section.

## Locked portfolio rules (from user)

- Initial capital: **$10,000**
- Max positions: **5**
- Sizing: **equal-weight** (target notional per new position = equity / max_positions, constrained by available cash)
- No leverage: cannot spend more cash than available
- Slippage: **0.05% per side**
  - Entry fill price = open * (1 + slippage)
  - Exit fill price = close * (1 - slippage)
- Commission: **$0.32 per order side**
  - $0.32 on entry, $0.32 on exit
- Monthly drawdown stop: for each calendar month, define `month_start_equity` on first trading day
  - If at any end-of-day close `equity < month_start_equity * (1 - 0.06)`, then **halt NEW entries** for the rest of that month
  - Continue to manage and exit open positions normally
- Per-trade risk cap: **<= 1% of month_start_equity**
  - Use stop distance from the strategy stop level: `risk_per_share = entry_fill - sl_level`
  - Shares must satisfy: `shares * risk_per_share <= 0.01 * month_start_equity`
  - Also satisfy equal-weight and cash constraints
- Shares: **integer shares (floor)**
- When >5 candidate entries on a day: rank by `signal_avg_dollar_volume_20d` descending; take top available slots

## Why we need a small refactor

Current backtest generates *executed* trades per symbol with a per-symbol no-reentry rule baked in (see the jump `i = exit_i + 1` in [`_simulate_symbol()`](../src/screener/backtest/engine.py:58)).

For a portfolio with max positions, some trades will be rejected due to slot/cash/DD halt. If we only simulate from the existing executed trade list, we incorrectly lose later opportunities on the same symbol (because the symbol-level simulator already skipped forward past the rejected trade’s exit).

So we need to generate **trade candidates per signal date** (including overlapping candidates), then let the portfolio simulator decide what actually gets entered. The portfolio simulator will enforce no re-entry per symbol *only after* a position is opened.

## Proposed architecture changes

### New module

- Add [`src/screener/backtest/portfolio.py`](../src/screener/backtest/portfolio.py:1)
  - `PortfolioConfig` dataclass (initial_capital, max_positions, slippage_bps, commission_per_side, monthly_dd_limit, monthly_risk_per_trade_pct)
  - `simulate_portfolio(candidates_df, prices_by_symbol, config, logger)`
    - Outputs:
      - `equity_curve`: daily series with columns (date, equity, cash, positions_value, drawdown_pct, halted_new_entries)
      - `fills_log`: portfolio-level fills (accepted/rejected candidates + reasons)
      - `portfolio_metrics`: total_return_pct, CAGR, max_drawdown_pct, exposure_pct, months_halted_count, turnover, etc.

### Backtest engine changes

- Update [`run_backtest()`](../src/screener/backtest/engine.py:234) to produce both:
  - `trade_candidates_df` (one row per signal-date candidate)
  - `trades_df` (subset that would happen under “unlimited capital, no portfolio constraints”) can remain for backward comparison, but dashboard equity uses portfolio simulation

- Add a function like `generate_trade_candidates_for_symbol(...)` near [`_simulate_symbol()`](../src/screener/backtest/engine.py:58):
  - Iterate every bar `i` (warmup … end-1)
  - If regime + signal condition match, build a candidate:
    - entry_date = i+1 open
    - exit_date/exit_reason via same TP/SL scanning logic already used
    - include `sl_level`, `tp_level`, `signal_avg_dollar_volume_20d`, `engine`, and required debug fields
  - Do **not** jump `i` forward to exit

### Summary JSON schema extension

Write additional fields into [`docs/data/backtest_summary.json`](../docs/data/backtest_summary.json:1) under a new `portfolio` key:

```json
{
  "portfolio": {
    "assumptions": {
      "initial_capital": 10000,
      "max_positions": 5,
      "slippage_pct_each_side": 0.0005,
      "commission_per_side": 0.32,
      "monthly_drawdown_limit_pct": 6.0,
      "monthly_risk_per_trade_pct": 1.0,
      "share_rounding": "floor",
      "entry_priority": "avg_dollar_volume_20d_desc",
      "risk_free_rate_annual": 0.0,
      "trading_days_per_year": 252
    },
    "metrics": {
      "total_return_pct": 0.0,
      "cagr_pct": 0.0,
      "max_drawdown_pct": 0.0,
      "exposure_pct": 0.0,
      "months_halted": 0,
      "sharpe": 0.0,
      "sortino": 0.0
    },
    "curve": {
      "dates": ["2020-01-02"],
      "equity": [10000.0],
      "drawdown_pct": [0.0]
    },
    "monthly_returns": [
      {"month": "2020-01", "return_pct": 0.0}
    ]
  }
}
```

Notes:
- `drawdown_pct` and `return_pct` are **percent points** (0–100) to match UI formatting via [`fmtPctPoints()`](../docs/app.js:16).
- `sharpe`/`sortino` are unitless ratios.

### Dashboard changes

- Replace the backtest chart logic in [`renderBacktestEquityChart()`](../docs/app.js:706):
  - Plot `portfolio.curve.equity` as the main line
  - Plot `portfolio.curve.drawdown_pct` as either:
    - a second dataset on a right-side axis, or
    - a separate small chart below (preferred for readability)
  - Update the chart note to describe portfolio assumptions (capital, sizing, costs, max positions, DD halt), not annual expectancy

- Add portfolio metric cards to the Backtesting tab:
  - Total return %, CAGR %, Max DD %, Exposure %, Months halted
  - Sharpe, Sortino

- Add a **Monthly returns** table:
  - Columns: Month, Return %
  - Data source: `portfolio.monthly_returns`

- Keep existing per-engine trade-stat cards from [`renderBacktestEngineCards()`](../docs/app.js:651).

### CLI / run script changes

- Extend [`scripts/run_backtest.py`](../scripts/run_backtest.py:1) with optional args matching the portfolio config:
  - `--initial-capital 10000`
  - `--max-positions 5`
  - `--slippage-pct 0.0005`
  - `--commission-per-side 0.32`
  - `--monthly-dd-limit-pct 6`
  - `--monthly-risk-per-trade-pct 1`

- Persist the chosen config into JSON meta/methodology so dashboard displays the exact assumptions used.

## Simulation mechanics (daily event loop)

Use a master daily index (benchmark trading days) and simulate:

1. Start-of-day: if `halted_new_entries` for this month, skip entries
2. Enter trades at *open* for candidates whose `entry_date == today`
   - Filter out candidates where symbol is already in an open position
   - Rank by `signal_avg_dollar_volume_20d` desc
   - Size shares = min(
     - equal-weight notional constraint,
     - cash constraint,
     - 1% monthly risk constraint based on `sl_level`
   )
   - Apply slippage + commission
3. End-of-day: exit positions whose `exit_date == today` at *close*
   - Apply slippage + commission
4. End-of-day equity mark-to-market: cash + sum(shares * close)
5. Apply monthly DD rule based on `month_start_equity`

## Metrics definitions

- Total return %: `(final_equity / initial_capital - 1) * 100`
- CAGR %: annualized based on first/last curve dates
- Max drawdown %: max peak-to-trough drawdown on the equity curve
- Exposure %: % of days with at least one open position
- Months halted: count of months where DD halt triggered
- Monthly return %: month-over-month return of equity using month-end equity values

Risk-adjusted metrics from daily equity curve (default `risk_free_rate_annual = 0`):
- Daily return: `r_t = equity_t / equity_{t-1} - 1`
- Sharpe (annualized): `mean(excess_daily) / std(excess_daily) * sqrt(252)`
- Sortino (annualized): `mean(excess_daily) / std(downside_excess_daily) * sqrt(252)` where downside uses `min(excess_daily, 0)`

## Deliverables checklist

- Portfolio simulator module + tests
- JSON schema update
- Dashboard chart + metric cards update
- Docs updated to explain the new curve and assumptions
