# Lessons and Notes

## Scope guardrails
- V1 is screening and research only.
- Avoid broker integration, execution, and intraday features.
- Keep deployment compatible with GitHub Pages.

## Data source realities
- yfinance reliability varies.
  - Fundamentals can be missing or inconsistent.
  - Handle missing values gracefully.
  - Produce diagnostics for skipped symbols and missing fields.
- Ticker formatting differences exist.
  - Support normalization for yfinance.
  - Preserve display tickers for the UI.

## Design preferences
- Keep modules small and cohesive.
- Make universe, regime rule, engines, and ranking swappable.
- Treat JSON as the primary contract with the frontend; always also export CSV.

## Automation and deployment gotchas
- yfinance can intermittently throttle or return partial datasets; scheduled jobs should tolerate occasional missing symbols and rely on diagnostics instead of failing the entire static publish.
- GitHub Actions `schedule` cron uses UTC, not local market time; choose cron windows that run after expected U.S. EOD data availability to reduce stale outputs.
- GitHub Pages serves static files only; publishing must target generated artifacts and frontend assets (no backend runtime assumptions).
- Artifact commits should be conditional (`commit only if changed`) to avoid noisy history from no-op runs.
- Stage only intended publish artifacts (for this project [`docs/data/latest.json`](docs/data/latest.json:1) and [`docs/data/latest.csv`](docs/data/latest.csv:1)).
- Keep [`data/cache/`](data/cache/:1) untracked and never commit cache files.
