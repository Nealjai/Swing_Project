# V1 Implementation Todo List

This checklist reflects the current project state.

1. [x] Write [`spec.md`](spec.md:1) with architecture, flows, and defaults.
2. [x] Write [`todolist.md`](todolist.md:1) aligned to phases and deliverables.
3. [x] Create and maintain core docs: [`readme.md`](readme.md:1), [`report.md`](report.md:1), and [`lessons.md`](lessons.md:1).
4. [x] Define output contracts for JSON and CSV artifacts.
5. [x] Create repository structure for pipeline and static site assets.
6. [x] Add configuration and defaults for V1 screening behavior.
7. [x] Implement universe loading from [`sp500.txt`](sp500.txt:1) with ticker normalization rules.
8. [x] Implement data acquisition with yfinance and local cache behavior.
9. [x] Implement indicators and SPY regime detection (close vs SMA200).
10. [x] Implement dual screening engines (bull + weak) and ranking output.
11. [x] Export latest static artifacts to [`docs/data/latest.json`](docs/data/latest.json:1) and [`docs/data/latest.csv`](docs/data/latest.csv:1).
12. [x] Build static dashboard assets in [`docs/`](docs/:1) for rendering latest results.
13. [x] Add automation workflow in [`.github/workflows/daily_screener.yml`](.github/workflows/daily_screener.yml:1) for scheduled/manual regeneration and artifact commit.

## Optional backlog (post-V1)

14. [ ] Expand universe management beyond the initial S&P 500 list.
15. [ ] Add richer dashboard UX or migrate frontend architecture if complexity grows.
