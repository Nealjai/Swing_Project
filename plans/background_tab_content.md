# Background: How the Scanner Thinks (Dual-Engine Scoring)

## High-Level Philosophy
This tool is designed to **rank stocks by opportunity**, not to give a binary yes/no answer.

- The scanner always starts with a **clean universe** (liquid, investable names).
- Then it evaluates each stock using the engine that best matches the **current market regime**.
- Instead of “hard gates” that instantly reject a stock, most signals now contribute to a **soft, normalized score**.
  - This makes rankings more stable.
  - It helps you find “almost there” names early (useful for building watchlists).

At the end, each stock has:
- A **final score** (0–100) used for ranking.
- Two internal axis scores:
  - **Leadership** (is it strong / trending / high-quality relative to the market?)
  - **Actionability** (is there a tradable setup *now or soon*?)
- A simple **`setup_tag`** label to quickly interpret the combination.

---

## Step 1: Market Regime (SPY vs SMA200)
The scanner defines the market regime using the benchmark (default: SPY).

- Compute the benchmark’s **SMA200**.
- Compare today’s benchmark close to that SMA200:
  - **Bull regime:** SPY close **above** SMA200
  - **Weak regime:** SPY close **below** SMA200

This regime check is intentionally simple and explainable. It acts as the “weather report” that decides what type of opportunities we prioritize.

---

## Step 2: Engine Selection
Exactly one engine is used for the main ranking each run:

- **Bull regime → Bull Engine**
  - Optimized for finding leaders that are setting up for breakouts and trend continuation.
- **Weak regime → Weak Engine**
  - Optimized for finding liquid names with **high-quality mean-reversion / reversal potential**, while still respecting trend and tradability.

---

## The Shift: From Hard Gates to Soft, Normalized Scoring
Older versions leaned on “pass/fail gates” (for example: if a condition fails, the stock is dropped).

The refactor moves most of that logic into scoring:

- Each feature is turned into a **0.0 to 1.0 component score** by comparing it to the current population of candidates.
- This comparison is **robust to outliers** (uses median/MAD) and then smoothly mapped using a sigmoid.
- Missing data doesn’t automatically kill a stock; it typically receives a **neutral** score for that feature.

Why this matters:
- In real markets, setups are rarely perfect.
- A soft model keeps ranking continuous and makes it easier to see *why* one stock outranks another.

---

## The Bull Engine (Continuation / Breakout Leaders)
**Goal:** Surface stocks that are already acting like leaders **and** are near an actionable entry.

The Bull Engine scores two axes:

### 1) Leadership (RS + Trend)
Leadership answers: *Is this name outperforming and trending in a healthy way?*

Inputs that contribute:
- **Relative Strength (RS):** strength vs the benchmark (SPY)
- **Trend:** how constructive the stock’s trend is

These are combined into a **Leadership score** (0–1).

### 2) Actionability (Breakout + Compression + Volume + Stage)
Actionability answers: *Is there a tradeable setup forming now?*

Inputs that contribute:
- **Breakout proximity:** is price near a valid pivot / breakout area?
- **Compression:** is volatility contracting (tightening action)?
- **Volume quality:** healthy volume behavior (including constructive accumulation signals)
- **Stage / structure quality:** whether the setup context resembles a more favorable stage

These are combined into an **Actionability score** (0–1).

### Bull Engine Final Score
The final Bull Engine score is a weighted blend of the two axes:

- **Final Score (0–100)** = 100 × (weighted Actionability + weighted Leadership)

(Exact weights may evolve, but the mental model stays the same: *leadership + tradable setup*.)

---

## The Weak Engine (Reversal / Mean-Reversion Candidates)
**Goal:** In weak markets, prioritize names that are liquid enough to trade and show **reversal potential**, while still favoring higher-quality leadership traits when available.

The Weak Engine also uses two axes (same interpretation, different inputs):

### 1) Actionability (Reversal + Extension + Capitulation)
Actionability answers: *Is this stretched/washed out enough to justify watching for a snapback?*

Inputs that contribute:
- **Reversal context:** oversold pressure (ex: RSI-based)
- **Extension:** how extended price is versus a lower band / downside stretch
- **Capitulation:** unusually high volume relative to recent typical volume (possible selling climax)

These combine into an **Actionability score** (0–1).

### 2) Leadership (Trend + Liquidity)
Leadership answers: *Is this a higher-quality candidate even within a weak tape?*

Inputs that contribute:
- **Trend vs SMA200:** whether the stock is above/below its long-term trend (and by how much)
- **Liquidity:** higher dollar volume is generally more tradable and less “random”

These combine into a **Leadership score** (0–1).

### Weak Engine Final Score
The final Weak Engine score is a weighted blend of:
- Actionability (reversal potential) and
- Leadership (trend + liquidity)

Result: you get a ranked list of the most compelling **potential reversal setups** that are also realistically tradable.

---

## Final Ranking: Score + `setup_tag`
After an engine computes the two axis scores:

1) **Final score (0–100)** is calculated from Leadership and Actionability.
2) A simple label, **`setup_tag`**, is assigned based on whether each axis is “high enough”.

### What the `setup_tag` Means
The tag is meant to be an at-a-glance interpretation of the two-axis model.

- **`Leadership`**
  - The stock scores strongly on Leadership, but Actionability is not yet high.
  - Typical use: strong names to monitor until they form cleaner entries.

- **`Actionable Breakout`**
  - The stock scores strongly on Actionability, but Leadership is not yet high.
  - Typical use: setup looks tradable, but be more selective / manage risk.

- **`Both`**
  - The stock is strong on both axes.
  - Typical use: highest-priority candidates.

- **`Watchlist`**
  - Neither axis is strongly above threshold, but it still passed the hard filters.
  - Typical use: early-stage ideas and “keep an eye on it” names.

Important note:
- The score is continuous; the tag is a simplification.
- Two stocks can share the same tag while having very different scores.

---

## Fundamental Quality Gates (Always On Hard Filters)
Even with soft scoring, the scanner still enforces a few **non-negotiable filters** to avoid untradeable names.

These hard filters are applied before scoring:
- **Minimum price**
- **Minimum market cap**
- **Minimum beta (1y)**
- **Minimum daily share volume**
- **Minimum average dollar volume (20d)**

If a stock fails these, it is excluded entirely (no score), because the data and trading characteristics are not suitable for this strategy.

---

## Practical How-To: How to Use This Page
- If you are newer:
  - Focus on **`setup_tag`** first, then use the chart to confirm.
  - Start with **`Both`**, then **`Leadership`** for watchlist building.

- If you are experienced:
  - Use the two-axis framing to match your style:
    - Momentum/continuation → favor **Leadership + Actionability** in Bull regimes
    - Mean-reversion → prioritize **Actionability** in Weak regimes, but keep liquidity/trend in mind
  - Treat the score as a ranking tool, not a guarantee.
