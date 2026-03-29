## Project Overview
- Name: US Market Regime Dual-Engine Stock Screener
- Purpose: Build a static web-based stock screening dashboard for U.S. equities that determines the overall market regime, switches to the appropriate screening engine, and displays ranked stock candidates for manual trading research.
- Type: Quantitative stock screening and research dashboard for U.S. stocks, focused on daily signal generation and analysis rather than trade execution.

## Key Features
- Market regime detection using a broad U.S. benchmark such as SPY and a 200-day moving average to classify the market as bullish or weak.
- Dual strategy engine:
  - Bull market mode: scan for momentum or trend-following setups such as stocks making new 20-day highs, breaking recent resistance, and showing strong relative strength.
  - Weak market mode: scan for oversold rebound setups such as RSI below 30 and price trading below the lower Bollinger Band, with optional reversal confirmation.
- Universe restricted to U.S.-listed common stocks only; exclude OTC securities, preferreds, warrants, rights, ETFs, ETNs, options, futures, crypto, and all derivatives.
- Broad market coverage across major U.S. exchange-listed stocks, with filters to remove low-quality or illiquid names.
- Daily data pipeline using free sources such as Yahoo Finance / yfinance for historical prices, volume, and basic fundamentals.
- Candidate ranking system based on regime fit, signal strength, liquidity, relative strength, and basic fundamental quality.
- Fundamental overlay showing selected metrics such as market cap, P/E, P/S, ROE, revenue growth, EPS growth, profit margin, and debt-related measures where available.
- Static dashboard UI hosted on GitHub Pages that reads generated JSON or CSV result files and displays:
  - current market state
  - active strategy engine
  - ranked candidates
  - technical indicators
  - basic fundamentals
  - configurable risk guidance such as stop loss and take profit levels
- Configurable scan settings for benchmark selection, moving average length, breakout lookback, RSI threshold, Bollinger Band settings, minimum price, minimum market cap, and minimum average daily volume.

## Constraints
- U.S.-listed common stocks only; exclude OTC securities, preferreds, warrants, rights, ETFs, ETNs, options, futures, crypto, and all derivatives.
- Screening and research only; do not implement broker integration, order routing, or auto-trading.
- V1 should be a static site suitable for GitHub Pages, without requiring a live backend server.
- Prefer free and open-source tools and services for development, testing, and deployment.
- Use end-of-day or daily-refreshed data in V1; intraday scanning is out of scope for the first version.
- Python should generate the screening output as static JSON/CSV files that the frontend can consume directly.
- The system should handle missing or inconsistent fundamental data gracefully.
- The project should remain modular so the data source, ranking logic, and UI can be upgraded later without rewriting the full system.

## Preferred Stack
- Language: Python for data collection, screening logic, indicator calculation, ranking, and file generation; JavaScript for the V1 frontend UI.
- Framework: Plain HTML, CSS, and JavaScript for V1 to keep the site lightweight, easy to deploy on GitHub Pages, and fast to iterate on. React/TypeScript can be considered later if the UI becomes significantly more complex.
- Database: No formal database in V1; use generated JSON/CSV files as the data layer. Optionally move to SQLite or PostgreSQL later if persistent history, watchlists, or backtesting records are needed.
- Deployment: GitHub Pages for the frontend and published screening results; Python scripts run locally or through GitHub Actions to regenerate and publish updated JSON/CSV files.