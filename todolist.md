# Backtest Rebuild Todo (2026-06-24)

- [x] Implement robust universe eligibility + reproducible random sampling in [`run_backtest()`](src/screener/backtest/engine.py:529).
- [x] Wire sampling CLI options and default official sizing preset behavior in [`parse_args()`](scripts/run_backtest.py:74).
- [x] Upgrade exit execution realism (gap-open + intraday TP/SL precedence) in [`simulate_portfolio()`](src/screener/backtest/portfolio.py:161).
- [x] Extend portfolio metric payload (Calmar, win rate, PF, expectancy, hold days) in [`simulate_portfolio()`](src/screener/backtest/portfolio.py:736).
- [x] Make yearly trade stats dynamic by dataset window in [`summarize_trades()`](src/screener/backtest/stats.py:90).
- [x] Update Backtesting compare/diagnostics UI fields in [`renderBacktestCompareStrip()`](docs/app.js:2019).
- [x] Persist fixed active scenario artifacts for Backtesting tab in [`main()`](scripts/run_backtest.py:424).
- [x] Run syntax compile + smoke backtest for both official scenarios via [`run_backtest.py`](scripts/run_backtest.py:1).
