# Trading Scanner Core Logic Summary

This document outlines the core mechanics of the trading scanner based on an analysis of the codebase.

## 1. Market Regime Determination

The market regime is the primary factor that determines which scanning engine is used.

*   **Criteria:** The regime is determined by comparing the closing price of the **SPY (S&P 500 ETF)** to its **200-day Simple Moving Average (SMA)**.
    *   If `SPY Close > 200-day SMA`, the regime is **"Bull"**.
    *   If `SPY Close <= 200-day SMA`, the regime is **"Weak"**.

*   **Source of Truth:** This logic is explicitly defined in [`docs/app.js`](docs/app.js:289-292) and is based on the `sma_regime_length` parameter in [`src/screener/config.py`](src/screener/config.py:23). The result of this check is stored in files like [`docs/data/market_condition.json`](docs/data/market_condition.json).

## 2. Scanning Engines

There are two distinct scanning engines, each designed for a specific market regime.

### a. Bull Engine (`bull.py`)

*   **Purpose:** To identify stocks in a strong uptrend that are poised for a breakout. It looks for classic chart patterns indicating consolidation before a potential move higher.
*   **Core Logic:**
    1.  **Pre-filters:** Applies basic filters from `config.py` (min price, market cap, volume, etc.).
    2.  **Uptrend Check:** Confirms the stock is in an uptrend (its close is above its own 200-day SMA).
    3.  **Pattern Recognition:** It attempts to detect two primary patterns:
        *   **Cup with Handle (CWH):** A bullish continuation pattern.
        *   **Volatility Contraction Pattern (VCP):** A pattern where price volatility decreases, often before a breakout.
    4.  **Scoring:** Candidates are scored based on two main components:
        *   **Leadership Score:** Measures the stock's relative strength (RS) compared to the market (SPY) and the strength of its trend.
        *   **Actionability Score:** Measures how "ready" the stock is for a breakout. This includes its proximity to a pivot price, the tightness of its price compression (volatility contraction), and trading volume patterns.
*   **Source Files:** [`src/screener/engines/bull.py`](src/screener/engines/bull.py)

### b. Weak Engine (`weak.py`)

*   **Purpose:** To identify oversold stocks that have the potential for a short-term rebound or mean-reversion rally.
*   **Core Logic:**
    1.  **Pre-filters:** Applies basic filters from `config.py`.
    2.  **Oversold Condition:** The primary filter is for stocks with a low **14-day Relative Strength Index (RSI)**, specifically below the `weak_rsi_threshold` of **30.0** (defined in `config.py`).
    3.  **Scoring:** Candidates are scored based on two main components:
        *   **Leadership Score:** Measures the stock's longer-term trend and liquidity. Even in a weak market, stronger stocks are preferred.
        *   **Actionability Score:** Measures the quality of the oversold setup. This includes:
            *   **Reversal:** How low the RSI is.
            *   **Extension:** How far the price is below its lower Bollinger Band.
            *   **Capitulation:** A measure of volume spike, indicating potential seller exhaustion.
*   **Source Files:** [`src/screener/engines/weak.py`](src/screener/engines/weak.py)

## 3. Engine Activation Logic

The active engine is determined by the market regime.

*   If Regime is **"Bull"** -> **Bull Engine** is active.
*   If Regime is **"Weak"** -> **Weak Engine** is active.

This is confirmed by the frontend code in [`docs/app.js`](docs/app.js:165-170) which reads the `regime` and `engine` from the data payload and displays a banner indicating which is active.
