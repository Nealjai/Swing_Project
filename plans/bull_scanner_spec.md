# Technical Specification: CWH and VCP Stock Scanner

## 1. Overview

**Goal:** Build a sophisticated stock scanner to identify swing-trade candidates from strong stocks that are forming or breaking out from Cup-with-Handle (CWH) or Volatility Contraction Pattern (VCP) bases.

**Focus:** The scanner's primary utility is to find stocks at actionable swing-trading stages:
- Near a pivot point.
- Actively breaking out.
- In a post-breakout pullback towards a key moving average (SMA20).
- Confirmed as "pullback-entry-ready."

**Key Feature:** A small triangle will be marked on the chart to visually flag the exact moment a pullback entry is confirmed, providing a clear signal for traders.

**Methodology:** The scanner will use rule-based pattern matching based on calculations from OHLCV data. It will not use any form of visual or AI-based chart recognition. The approach is to calculate measurable features from the data to approximate and score how well a stock's price action matches the ideal characteristics of CWH or VCP patterns.

## 2. Core Scanner Logic Flow

The scanner will process each stock through the following logical steps:

1.  **Relative Strength Filter:** First, filter for stocks demonstrating superior relative strength compared to the S&P 500 (SPY).
2.  **Pattern Detection:** Detect whether the price structure matches the criteria for a CWH or VCP pattern.
3.  **Pivot Identification:** Identify the key pivot or resistance zone for the detected pattern.
4.  **State Determination:** Determine the current state of the stock relative to the pattern (e.g., forming, near pivot, breakout).
5.  **Pullback Monitoring:** After a breakout is confirmed, activate a dedicated engine to monitor for a constructive pullback.
6.  **Entry Flagging:** Mark a triangle on the chart if and only if a valid pullback entry is confirmed.
7.  **Ranking & Sorting:** Rank and sort all qualifying candidates based on the quality of the pattern and the actionability of its current trade stage.

## 3. Detailed Logic and Calculations

### 3.1. Relative Strength vs. SPY

**Purpose:** To use relative strength as a primary filter for market leadership. Only stocks outperforming the market will be considered.

**Calculations:**
- `rs_line = (stock_close / spy_close) * 100`
- `rs_return_20d = (stock_return_20d / spy_return_20d) - 1`
- `rs_return_60d = (stock_return_60d / spy_return_60d) - 1`
- `rs_return_90d = (stock_return_90d / spy_return_90d) - 1`
- `rs_line_sma_short = SMA(rs_line, 10)`
- `rs_line_sma_long = SMA(rs_line, 50)`

**Pseudocode Logic:**
```pseudocode
// Determine if RS is in a positive trend
rs_trending_up = (rs_line_sma_short > rs_line_sma_long)

// Main filter condition
rs_pass = (rs_return_20d > 0) AND (rs_return_60d > 0) AND (rs_trending_up)

// Scoring for ranking purposes
rs_score = 0
IF (rs_return_20d > 0) THEN rs_score += 1
IF (rs_return_60d > 0) THEN rs_score += 1
IF (rs_return_90d > 0) THEN rs_score += 1
IF (rs_trending_up) THEN rs_score += 2
```

**Variables:**
- `rs_line`, `rs_return_20d`, `rs_return_60d`, `rs_return_90d`, `rs_line_sma_short`, `rs_line_sma_long`, `rs_trending_up`, `rs_score`, `rs_pass`.

### 3.2. Cup with Handle (CWH) Pattern Logic

**Purpose:** To detect if a stock is forming a valid CWH pattern.

**Calculations:**
- Identify `left_peak`, `cup_bottom`, `right_peak`.
- `cup_depth_pct = (left_peak - cup_bottom) / left_peak`
- `cup_duration_bars = bar_index(right_peak) - bar_index(left_peak)`
- `right_recovery_pct = right_peak / left_peak`
- `bottom_zone_width` = Number of bars spent near the `cup_bottom`.
- Identify `handle_start`, `handle_high`, `handle_low`.
- `handle_depth_pct = (handle_high - handle_low) / handle_high`
- `handle_duration_bars`
- `cup_midpoint = cup_bottom + 0.5 * (left_peak - cup_bottom)`
- `pivot_price = handle_high`

**Pseudocode Logic:**
```pseudocode
// Pre-condition: Ensure a prior uptrend exists (e.g., price > SMA200).

// Rule 1: Cup should be rounded, not V-shaped.
is_rounded_cup = (bottom_zone_width > min_required_bars)

// Rule 2: Handle must form in the upper half of the cup.
is_handle_high_enough = (handle_low > cup_midpoint)

// Rule 3: Handle should be a smaller, shorter consolidation.
is_handle_smaller = (handle_depth_pct < cup_depth_pct) AND (handle_duration_bars < cup_duration_bars)

// Final check for a valid CWH candidate
is_cwh_candidate = (prior_uptrend_exists) AND
                   (is_rounded_cup) AND
                   (right_recovery_pct > 0.90) AND // Right side recovered near the peak
                   (handle_exists) AND
                   (is_handle_high_enough) AND
                   (is_handle_smaller)
```

**Variables:**
- `left_peak`, `cup_bottom`, `right_peak`, `cup_depth_pct`, `cup_duration_bars`, `bottom_zone_width`, `handle_start`, `handle_high`, `handle_low`, `handle_depth_pct`, `handle_duration_bars`, `cup_midpoint`, `pivot_price`, `cwh_score`, `is_cwh_candidate`.

### 3.3. Volatility Contraction Pattern (VCP) Logic

**Purpose:** To detect if a stock is exhibiting a VCP, characterized by tightening volatility and pullbacks.

**Calculations:**
- Identify 2-4 swing high/low pairs within the base.
- For each contraction `n`:
  - `contraction_depth_pct_n = (contraction_high_n - contraction_low_n) / contraction_high_n`
  - `contraction_duration_bars_n`
- Volatility Contraction Metrics:
  - `atr_contraction_ratio = ATR(10) / ATR(50)`
  - `stddev_return_10d`, `stddev_return_30d`
  - `stddev_contraction_ratio = stddev_return_10d / stddev_return_30d`
- `pivot_price` = Resistance high of the final, tightest contraction.

**Pseudocode Logic:**
```pseudocode
// Pre-condition: Ensure a prior uptrend exists.

// Find 2 to 4 pullback contractions.
contractions = find_swing_high_low_pairs()
IF count(contractions) < 2 OR count(contractions) > 4 THEN is_vcp_candidate = false

// Rule 1: Contractions should generally get smaller.
depth_is_tightening = (contraction_depth_pct_2 < contraction_depth_pct_1) AND ... // Allow some noise

// Rule 2: Volatility should contract from left to right.
volatility_is_tightening = (stddev_contraction_ratio < 0.7) OR (atr_contraction_ratio < 0.7)

// Rule 3: Volume should dry up, especially in the final contraction.
final_contraction_volume_low = (volume_in_last_contraction < avg_volume_base)

// Final check for a valid VCP candidate
is_vcp_candidate = (prior_uptrend_exists) AND
                   (depth_is_tightening) AND
                   (volatility_is_tightening) AND
                   (final_contraction_volume_low)
```

**Variables:**
- `contraction_1_depth_pct`, `contraction_2_depth_pct`, etc.
- `contraction_sequence_score`, `atr_contraction_ratio`, `stddev_contraction_ratio`, `volume_dryup_score`, `pivot_price`, `vcp_score`, `is_vcp_candidate`.

### 3.4. Volume Quality Logic

**Purpose:** To use volume behavior to qualify the quality of a base and its breakout.

**Calculations:**
- `volume_dryup_ratio = SMA(volume, 10) / SMA(volume, 50)`
- `avg_up_volume_20` / `avg_down_volume_20`
- `up_down_volume_ratio = avg_up_volume_20 / avg_down_volume_20`
- `breakout_volume_ratio = breakout_volume / SMA(volume, 20)`
- `pocket_pivot_flag`: A flag for days with significant up-volume.

**Pseudocode Logic:**
```pseudocode
// Score for volume dry-up during base formation
volume_quality_score = 0
IF volume_dryup_ratio < 0.6 THEN volume_quality_score += 2 // Strong dry-up

// Score for signs of accumulation
IF up_down_volume_ratio > 1.5 THEN volume_quality_score += 1

// On breakout, score the volume expansion
IF breakout_flag IS true AND breakout_volume_ratio > 2.0 THEN
    volume_quality_score += 3
```

**Variables:**
- `volume_dryup_ratio`, `up_down_volume_ratio`, `pocket_pivot_flag`, `breakout_volume_ratio`, `volume_quality_score`.

### 3.5. Base Depth Logic

**Purpose:** To use the depth of the overall base as a quality factor.

**Calculations:**
- `high_52w`
- `base_depth_pct = (high_52w - base_low) / high_52w`

**Pseudocode Logic:**
```pseudocode
base_depth_score = 0
IF base_depth_pct > 0.15 AND base_depth_pct < 0.35 THEN
    base_depth_score = 2 // Ideal depth
ELSE IF base_depth_pct > 0.10 AND base_depth_pct < 0.50 THEN
    base_depth_score = 1 // Acceptable depth
ELSE
    base_depth_score = -1 // Too shallow or too deep
```

**Variables:**
- `high_52w`, `base_depth_pct`, `base_depth_score`.

### 3.6. Pivot / Resistance Logic

**Purpose:** To identify a meaningful pivot price based on resistance clustering.

**Calculations:**
- Detect all `swing_highs`.
- Cluster nearby `swing_highs` into a `resistance_zone`.
- `pivot_price` = The highest high in the most tested resistance zone.
- `pivot_test_count` = Number of touches in the zone.
- `pivot_distance_pct = (pivot_price - current_close) / pivot_price`

**Pseudocode Logic:**
```pseudocode
// Determine the stock's current stage relative to the pivot
IF breakout_flag IS true THEN
    // Defer to pullback engine for state
    pattern_stage = pullback_entry_state
ELSE IF pivot_distance_pct < 0.02 THEN
    pattern_stage = 'near-pivot'
ELSE
    pattern_stage = 'early-stage'
```

**Variables:**
- `swing_highs`, `resistance_zone`, `pivot_price`, `pivot_test_count`, `pivot_distance_pct`, `pivot_quality_score`, `pattern_stage`.

### 3.7. Breakout Logic

**Purpose:** To treat the breakout as a state and measure its quality.

**Calculations:**
- `breakout_flag = close > pivot_price`
- `breakout_strength_pct = (close - pivot_price) / pivot_price`
- `close_location_in_range = (close - low) / (high - low)`

**Pseudocode Logic:**
```pseudocode
// Determine the breakout state
IF breakout_flag AND days_since_breakout <= 3 THEN
    breakout_state = 'breakout'
ELSE IF breakout_flag AND days_since_breakout > 3 THEN
    breakout_state = 'post_breakout_watch'
ELSE
    breakout_state = 'pre_breakout'
```

**Variables:**
- `breakout_flag`, `breakout_strength_pct`, `breakout_volume_ratio`, `close_location_in_range`, `breakout_state`.

### 3.8. Pullback Engine

**Purpose:** To identify low-risk pullback entries after a breakout, which is a primary goal of the scanner.

**Activation:** This logic only runs if `breakout_state` is `post_breakout_watch`.

**Calculations:**
- `sma20 = SMA(close, 20)`
- `distance_to_sma20_pct = (close - sma20) / sma20`
- `pullback_volume_ratio = SMA(volume, 3) / SMA(volume, 20)`
- `support_rebound_flag`: A flag for bullish reversal candles near support.

**Pseudocode Logic:**
```pseudocode
pullback_entry_state = 'none'
entry_triangle_flag = false

IF breakout_state IS 'post_breakout_watch' THEN
    // Condition 1: Price has pulled back to near the SMA20
    is_near_support = (distance_to_sma20_pct is between -0.02 and 0.02)

    // Condition 2: Volume on the pullback is quiet
    is_volume_quiet = (pullback_volume_ratio < 1.0)

    // Condition 3: A rebound candle pattern appears (e.g., hammer, bullish engulfing)
    support_rebound_flag = check_for_rebound_candle_pattern_at(sma20)

    // Update state
    IF is_near_support AND is_volume_quiet THEN
        pullback_entry_state = 'post-breakout-watch' // Watching for entry
    END IF

    // Confirmation for entry
    IF pullback_entry_state IS 'post-breakout-watch' AND support_rebound_flag THEN
        pullback_entry_state = 'pullback-entry-ready'
        entry_triangle_flag = true
        entry_triangle_price = low_of_rebound_day
        entry_triangle_date = date_of_rebound_day
    END IF
END IF
```

**Variables:**
- `sma20`, `distance_to_sma20_pct`, `pullback_volume_ratio`, `support_rebound_flag`, `pullback_entry_state`, `entry_triangle_flag`, `entry_triangle_price`, `entry_triangle_date`.

## 4. Ranking and Sorting

**Purpose:** To organize the scanner output so the most actionable ideas are presented first.

**Output Fields per Stock:**
- `pattern_type`, `pattern_quality_score`, `pattern_stage`, `rs_score`, `contraction_score`, `volume_quality_score`, `base_depth_score`, `pivot_quality_score`, `breakout_state`, `pivot_price`, `pivot_distance_pct`, `breakout_strength_pct`, `pullback_entry_state`.

**Sorting Priority:**
1.  **Primary Sort:** `pattern_stage` in the following custom order:
    1.  `pullback-entry-ready`
    2.  `post-breakout-watch`
    3.  `breakout`
    4.  `near-pivot`
    5.  `early-stage`
2.  **Secondary Sort (within each stage):**
    - `pattern_quality_score` (descending)
    - `rs_score` (descending)
    - `volume_quality_score` (descending)

## 5. Best-Practice Notes

- The scanner should favor swing-trade usability over pattern purity.
- Use loose minimum criteria for initial inclusion, then use the scoring system to rank the best setups higher.
- Not every condition should be a hard filter; most should contribute to a composite quality score.
- The logic should remain flexible, acknowledging that CWH and VCP are approximations of ideal market structure.
