
# Specification: Market Condition Tab

## 0. Addendum (2026-08-05): Contract alignment to current runtime

### Goal
Align this spec with the actual implementation currently running in [`scripts/run_daily.py`](scripts/run_daily.py:314), [`src/screener/tracker.py`](src/screener/tracker.py:626), and [`src/screener/market_condition.py`](src/screener/market_condition.py:198).

### Tracker inclusion + lifecycle rules (current)
- Include only symbols that satisfy all conditions on the run day:
  - `intent == trade`
  - `rank <= 10`
  - `risk.position_sizing.max_shares > 0`
- Quality gate is hybrid and dynamic (not fixed 0.90/0.58 only):
  - strict route: leadership dynamic quantile gate (`q90`) + actionability floor (`>= 0.58`)
  - playbook-aware relaxed route:
    - `PULLBACK_ENTRY` / `TIGHT_BASE` / `LEADER_PULLBACK`: leadership `>= q85`, actionability `>= 0.55`
    - `BREAKOUT`: leadership `>= q88`, actionability `>= 0.58`
- Tracker lifecycle is position-state based:
  - records remain `active` until stop-loss / trailing-stop / time-stop logic exits the position
  - exited records become `inactive`
  - max tracked window is capped at 15 trading days in runtime calculations

### Tracker data contract (current)
Artifact: [`docs/data/tracker.json`](docs/data/tracker.json:1)

Top-level structure:
- `meta` (generated timestamp, rules, counts)
- `active` (active records)
- `inactive` (inactive/exited records)
- `dropped` (backward-compat alias of `inactive`)
- `items` (combined active + inactive list)

Representative record fields (runtime-generated):
- identity/context: `symbol`, `engine`, `playbook_id`, `playbook_label`, `regime_label`, `intent`
- capture/entry: `capture_date_utc`, `entry_date_utc`, `entry_price`, `capture_close`, `current_close`
- performance/state: `return_since_capture_pct`, `days_tracked_trading`, `expiry_date_utc`, `status`, `position_state`
- risk/execution: `signal_close`, `signal_atr14`, `stop_loss`, `activation_level`, `trailing_stop_offset`, `trail_stop_price`
- lifecycle events: `activated`, `activation_date_utc`, `activation_price`, `partial_exit_done`, `partial_exit_fraction`, `highest_close_since_entry`
- exit/status labels: `exit_reason`, `exit_date_utc`, `exit_price`, `status_tags`, `status_tag`, `last_updated_utc`

### Runtime integration points
- Tracker writer: [`update_tracker_file()`](src/screener/tracker.py:626)
- Daily pipeline integration: [`main()`](scripts/run_daily.py:314)
- Frontend consumer:
  - fetch paths in [`docs/app.js`](docs/app.js:3569)

### Non-goals
- No behavior change from this documentation update.
- No alteration to the existing output contracts beyond documenting current truth.

## 0. Addendum (2026-04-18): Normalized dual-engine scoring refactor

### Summary
- Bull and weak engines were refactored from hard RS/pattern gates to a robust cross-sectional normalized scoring model.
- Production ranking now uses a single normalized `score` field.
- Legacy engine score logic is retained only under `debug_metrics.legacy_score` for comparison.
- Added `setup_tag` output labels: `Both`, `Actionable Breakout`, `Leadership`, `Watchlist`.

### Hard filters (kept)
- `min_price`
- `min_market_cap`
- `min_beta_1y`
- `min_volume`
- `min_avg_dollar_volume_20d` (new)

### Shared normalization layer
Implemented in `src/screener/engines/scoring.py`:
- `to_float(value)`
- `clamp01(value)`
- `sigmoid(value)`
- `robust_unit_score(value, population, invert=False, neutral=0.5)`

Normalization behavior:
- Uses median + MAD for robust z-scoring.
- Squashes to `[0,1]` via sigmoid.
- Returns neutral score (`0.5`) when feature value is missing or population is too small.
- Supports `invert=True` for lower-is-better factors.

### Bull engine v2 model
- Leadership axis:
  - `rs_component` (RS strength/trend)
  - `trend_component` (distance vs SMA200)
  - `leadership_score = 0.6*rs + 0.4*trend`
- Actionability axis:
  - `breakout_component`
  - `compression_component` (inverted ATR10/ATR50)
  - `volume_component`
  - `stage_component`
  - `actionability_score = 0.4*breakout + 0.25*compression + 0.2*volume + 0.15*stage`
- Final score:
  - `score = 100 * (0.55*actionability + 0.45*leadership)`

### Weak engine v2 model
- Actionability axis:
  - `reversal_component`
  - `extension_component`
  - `capitulation_component`
  - `actionability_score = 0.45*reversal + 0.35*extension + 0.20*capitulation`
- Leadership axis:
  - `trend_component`
  - `liquidity_component`
  - `leadership_score = 0.70*trend + 0.30*liquidity`
- Final score:
  - `score = 100 * (0.60*actionability + 0.40*leadership)`

### Runtime/export/backtest alignment
- Daily runtime passes `min_avg_dollar_volume_20d` into both engines.
- Exported scanner settings include `min_avg_dollar_volume_20d`.
- Backtest common eligibility now enforces `avg_dollar_volume_20d >= min_avg_dollar_volume_20d`.

### Validation
- Added unit tests for robust normalization edge cases under `tests/test_scoring.py`.
- Smoke backtest completed successfully using test universe via `scripts/run_backtest.py`.

---

## 1. Architecture Overview

This document outlines the plan to add a new "Market Condition" tab to the application. The new feature will introduce a dedicated backend module for market analysis and a corresponding frontend component for visualization.

The overall architecture will be updated as follows:

1.  **Backend**: A new module, `src/screener/market_condition.py`, will be created to encapsulate all logic for calculating the market regime, distribution days (DD), and follow-through days (FTD).
2.  **Daily Script**: The existing `scripts/run_daily.py` will be modified to import and execute the new market condition script.
3.  **Data Output**: The result will be saved as a new JSON file: `docs/data/market_condition.json`.
4.  **Frontend**: The `docs/app.js` will fetch this new data file. A new tab will be added to `docs/index.html`, and `app.js` will render the indicators and a new SPY chart in this tab.
5.  **Charting**: The project currently uses `Chart.js`. For consistency, the new SPY chart will also be implemented using `Chart.js`, not `lightweight-charts`.

### Mermaid Diagram: System Flow

```mermaid
graph TD
    A[scripts/run_daily.py] --> B{Generate Market Condition};
    B --> C[src/screener/market_condition.py];
    C --> D{Fetch SPY & VIX Data};
    D --> E[src/screener/data.py];
    C --> F{Calculate Regime, DD, FTD};
    F --> G[Save to docs/data/market_condition.json];
    
    subgraph Frontend
        H[docs/index.html]
        I[docs/app.js]
        J[docs/styles.css]
    end

    G --> I;
    I --> H;
```

## 2. Data Structure

The [`docs/data/market_condition.json`](docs/data/market_condition.json:1) file currently follows this structure:

```json
{
  "generated_at": "YYYY-MM-DDTHH:MM:SS+00:00",
  "regime_label": "Bull",
  "signals": {
    "spy_close_above_sma200": true,
    "spy_close_above_sma50": true,
    "sma50_up_10d": true
  },
  "spy_close": 450.75,
  "vix_close": 15.2,
  "distribution_day_count_25d": 3,
  "distribution_day_count_25d_series": [0, 1, 1, 2],
  "distribution_day_dates": ["2023-10-26"],
  "follow_through_day_dates": ["2023-11-02"],
  "chart_markers": {
    "distribution_days": [
      { "date": "2023-10-26", "price": 413.72 }
    ],
    "follow_through_days": [
      { "date": "2023-11-02", "price": 431.75 }
    ]
  },
  "spy_history": {
    "dates": ["2023-01-01", "..."],
    "open": [440.1, "..."],
    "high": [443.2, "..."],
    "low": [437.8, "..."],
    "close": [441.7, "..."],
    "volume": [73000000, "..."],
    "sma50": [430.5, "..."],
    "sma200": [400.2, "..."]
  }
}
```

## 3. Backend Implementation (current)

### 3.1 Market condition builder
- Implemented by [`get_market_condition()`](src/screener/market_condition.py:198).
- Downloads SPY/VIX history via [`_download_history()`](src/screener/market_condition.py:37).
- Computes indicators via [`_add_spy_indicators()`](src/screener/market_condition.py:66).
- Produces regime label via [`_calculate_regime_signals()`](src/screener/market_condition.py:75) + [`_determine_regime()`](src/screener/market_condition.py:84).
- Produces DD/FTD markers via [`_distribution_days()`](src/screener/market_condition.py:100) and [`_follow_through_days()`](src/screener/market_condition.py:118).

### 3.2 Daily pipeline integration
- Daily runtime calls market condition generation in [`main()`](scripts/run_daily.py:396).
- Result is written to [`docs/data/market_condition.json`](docs/data/market_condition.json:1) in [`main()`](scripts/run_daily.py:570).
- Daily runtime also writes tracker payload via [`update_tracker_file()`](src/screener/tracker.py:626) and screener payload via [`export_outputs()`](src/screener/export.py:30).

## 4. Frontend Implementation

### 4.1. `docs/index.html` Changes

-   Add a new tab button and tab panel.

```html
<!-- In nav.tabs -->
<button id="tabBtnMarketCondition" class="tab-btn" data-tab="marketCondition" type="button">Market Condition</button>
<button id="tabBtnScreener" class="tab-btn active" data-tab="screener" type="button">Screener Result</button>
<button id="tabBtnBackground" class="tab-btn" data-tab="background" type="button">Background</button>
<button id="tabBtnHistory" class="tab-btn" data-tab="history" type="button">Backtesting</button>

<!-- After </section> for tabScreener -->
<section id="tabMarketCondition" class="tab-panel" aria-labelledby="tabBtnMarketCondition">
    <section class="summary-grid">
        <div class="card">
            <h3>Regime</h3>
            <p id="mcRegime">-</p>
        </div>
        <div class="card">
            <h3>SPY Close</h3>
            <p id="mcSpyClose">-</p>
        </div>
        <div class="card">
            <h3>VIX Close</h3>
            <p id="mcVixClose">-</p>
        </div>
        <div class="card">
            <h3>Distribution Days</h3>
            <p id="mcDdCount">-</p>
        </div>
        <div class="card">
            <h3>Follow-Through Days</h3>
            <p id="mcFtdCount">-</p>
        </div>
    </section>
    <section class="card">
        <h2>SPY Chart (1Y)</h2>
        <canvas id="marketConditionChart" height="120"></canvas>
    </section>
</section>
```

### 4.2. `docs/app.js` Changes

-   Fetch `market_condition.json`.
-   Render the indicators and the new chart.

```javascript
// In state object
let state = {
    // ... existing state
    marketCondition: {
        loaded: false,
        loading: false,
        data: null,
        error: null,
    },
    marketConditionChart: null,
};

// New function to load market condition data
async function loadMarketConditionData() {
    if (state.marketCondition.loaded || state.marketCondition.loading) return;
    state.marketCondition.loading = true;
    
    try {
        const res = await fetch(`data/market_condition.json?t=${Date.now()}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        state.marketCondition.data = data;
        state.marketCondition.loaded = true;
        renderMarketCondition(data);
    } catch (err) {
        state.marketCondition.error = err.message;
        // Handle error display
    } finally {
        state.marketCondition.loading = false;
    }
}

// New function to render the data
function renderMarketCondition(data) {
    document.getElementById('mcRegime').textContent = data.regime;
    document.getElementById('mcSpyClose').textContent = fmtNumber(data.spy_close);
    document.getElementById('mcVixClose').textContent = fmtNumber(data.vix_close);
    document.getElementById('mcDdCount').textContent = fmtInt(data.distribution_day_count);
    document.getElementById('mcFtdCount').textContent = fmtInt(data.ftd_count);

    renderMarketConditionChart(data.chart_data);
}

// New function to render the chart
function renderMarketConditionChart(chartData) {
    const ctx = document.getElementById('marketConditionChart');
    destroyChart(state.marketConditionChart);

    // Scatter data for markers
    const ddPoints = chartData.distribution_days.map(d => ({ x: d.date, y: d.price }));
    const ftdPoints = chartData.follow_through_days.map(d => ({ x: d.date, y: d.price }));

    state.marketConditionChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: chartData.dates,
            datasets: [
                { label: 'SPY Close', data: chartData.spy_close, borderColor: '#3b82f6', borderWidth: 2, pointRadius: 0 },
                { label: 'SMA50', data: chartData.sma50, borderColor: '#22c55e', borderWidth: 1.5, borderDash: [4, 4], pointRadius: 0 },
                { label: 'SMA200', data: chartData.sma200, borderColor: '#e879f9', borderWidth: 1.5, borderDash: [2, 4], pointRadius: 0 },
                {
                    type: 'scatter',
                    label: 'Distribution Day',
                    data: ddPoints,
                    backgroundColor: 'red',
                    pointStyle: 'triangle',
                    rotation: 180,
                    radius: 6,
                },
                {
                    type: 'scatter',
                    label: 'Follow-Through Day',
                    data: ftdPoints,
                    backgroundColor: 'lime',
                    pointStyle: 'triangle',
                    radius: 6,
                }
            ]
        },
        options: { /* ... standard chart options ... */ }
    });
}

// In boot() function
async function boot() {
    // ...
    loadMarketConditionData(); // Load the new data on boot
    // ...
}

// In activateTab() function
function activateTab(buttons, panels, key) {
    // ...
    if (key === 'marketCondition') {
        loadMarketConditionData();
    }
    // ...
}
```

### 4.3. `docs/styles.css` Changes

-   Add basic styling for the new components.

```css
/* In docs/styles.css */

#tabMarketCondition .summary-grid {
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
}
```

This plan provides a comprehensive overview of the required changes to implement the "Market Condition" tab.

## 5. Screener Result Tab

This section outlines the design for the updated screener result tab, which will incorporate a dual-view layout to enhance data visualization and analysis.

### 5.1. View Layouts

The screener result tab will feature two distinct layouts:

1.  **List View (Default):** A detailed, scrollable list of stocks matching the screener criteria. Each row will display comprehensive data for a single stock. This remains the default view.
2.  **Chart View:** A compressed list showing only the stock symbol on the left. The right-hand side will be dominated by a large candle chart displaying the historical price data for the selected symbol.

### 5.2. UI Components

-   **View Switcher:** A set of buttons will be added to the top of the screener result tab to allow users to toggle between "List View" and "Chart View".
-   **Chart Container:** A dedicated container will house the candle chart in the "Chart View".

### 5.3. Candle Chart

The candle chart will be a key feature of the "Chart View" and will reuse the existing TradingView-style implementation from the market condition tab to ensure consistency. It will display the main candlestick series and any selected moving averages as overlays. It will not include a separate line chart for "Adj Close".

-   **Data:** The chart will be populated with 3 years of daily candle data for the selected stock.
-   **Details Panel:** Above the chart, a panel will display key details for the selected symbol: Current Price, Stop Loss, Take Profit, ATR14, ROE, P/E, Revenue Growth QoQ, Revenue Growth YoY, Engine, and Score.
-   **Indicator Controls:** A set of checkboxes will be available to toggle various technical indicators on the chart: SMA20, SMA50, SMA200, EMA9, EMA21, and Volume. The candlestick series is always visible and not toggleable.
-   **Chart Legend:** Positioned below the indicator controls and above the chart, this component displays the name and color of each active, toggleable indicator (e.g., SMAs, EMAs). It will not include entries for the primary candlestick series or the volume bars.

### 5.4. Mermaid Diagram: Chart View Layout

The following diagram illustrates the layout of the "Chart View":

```mermaid
graph TD
    subgraph Screener Result Tab
        direction LR
        
        subgraph Viewport
            direction TB

            A[View Switcher: [List View] / [Chart View]]
            
            subgraph Chart View Layout
                direction LR
                B[Stock List]
                C[Chart Area]
            end
            
            A --> Chart View Layout
        end
    end

    subgraph B [Stock List]
        direction TB
        B1[Symbol 1]
        B2[Symbol 2]
        B3[Symbol 3]
    end

    subgraph C [Chart Area]
        direction TB
        C1[Details Panel]
        C2[Indicator Controls]
        C2_5[Chart Legend]
        subgraph Chart Panes
            direction TB
            C3[Main Chart (Candles + Overlays)]
            C4[Volume Pane]
        end
    end
```
