# Weak Engine (Weak Regime) — Finalized Plan (v1)

This document formalizes the **Weak Engine** scanning + ranking logic for **long-only swing trades** in weak market regimes.

It mirrors the Bull Engine flow:

1) Screener runs (weak regime only) → computes normalized scores → ranks candidates.
2) Tags (🏆/⚡/👀) are derived from the two universal scores.
3) Top candidates with strong tags are added to the tracker.
4) The UI shows which **playbook** produced each candidate.

---

## 1) Non-negotiable philosophy (bear-market survival)

A weak-regime engine must avoid becoming a **falling-knife factory**.

**Rule:** Oversold alone is not actionable.

Therefore, the Weak Engine must include a simple **turn / reclaim confirmation** before awarding ⚡ (entry-ready).

---

## 2) Outputs (contract)

Every Weak Engine candidate must output:

- `engine = "weak"`
- `playbook_id` (one of the 3 below)
- `playbook_label` (human label for UI)
- `leadership_score` in [0..1]
- `actionability_score` in [0..1]
- `score = 100 * (wA*actionability_score + wL*leadership_score)`
- `reasons` (plain-English explanations)

Tags are **not** computed in Python; the web derives icons using the existing rules in [`buildCandidateTagCell()`](../docs/app.js:70).

---

## 3) Playbooks (3) — purpose + one-line definition

### A) Defensive Relative Strength (playbook_id = `DEF_RS`)
**Purpose:** Own the names institutions hide in during weak tape (structurally healthy, tradable volatility).

**Definition:** Above key moving averages, controlled ATR%, liquid enough to exit.

### B) Capitulation → Reclaim (playbook_id = `CAP_RECLAIM`)
**Purpose:** Tactical bounces after forced selling finishes.

**Definition:** Oversold + liquidity + **reclaim trigger** (must prove a turn before entry readiness).

### C) Leader Pullback (playbook_id = `LEADER_PB`)
**Purpose:** Buy pullbacks in the strongest names that remain intact even in weak markets.

**Definition:** Strong structure with a controlled pullback into support (not a washed-out breakdown).

---

## 4) Minimum additional calculations required (to be sound)

These are required for v1.

### 4.1 Reclaim / Turn trigger (required)
Compute a simple reclaim score from existing indicators (no heavy history required):

- `reclaim_bb = 1 if close > bb_lower else 0`
- `reclaim_ema = 1 if close > ema9 else 0`
- `reclaim_sma20 = 1 if close > sma20 else 0`
- `reclaim_score = max(reclaim_bb, reclaim_ema, reclaim_sma20)`

**Policy:** In weak engine, ⚡ should only be possible if `reclaim_score == 1`.

This prevents awarding entry-ready tags to persistent downtrends.

### 4.2 Volatility / gap-risk proxy (required)
Use existing ATR14:

- `atr_pct = atr14 / close`

Use it as an inverted feature in scoring (lower is better) and optionally apply a hard ceiling (`atr_pct <= max_atr_pct`).

### 4.3 Beta filter correction (required)
Current weak engine hard filter requires `beta_1y >= min_beta_1y`.

In weak regimes this is usually a landmine selector.

**v1 policy:** remove beta as a required minimum for weak engine (beta-neutral), or use a `max_beta_1y` cap.

---

## 5) Scoring framework (simple + consistent)

We keep the **two-score model** used across engines:

- `leadership_score`: “Is this stock strong/quality *for the playbook*?”
- `actionability_score`: “Is it actionable *today* (entry readiness) *for the playbook*?”

Then:

- `score = 100 * (0.60 * actionability_score + 0.40 * leadership_score)` (default weights; adjustable)

### 5.1 Leadership score (weak tape definition)
Leadership in weak tape should reward **tradability + structure**, not “deeply oversold.”

Core components (normalized with robust_unit_score):

- Structure: `close/sma200 - 1` (for DEF_RS and LEADER_PB; low weight for CAP_RECLAIM)
- Liquidity: `avg_dollar_volume_20d` (always)
- Safety: `atr_pct` (invert=True)

### 5.2 Actionability score (weak tape definition)
Actionability must include **reclaim_score**.

Core components (normalized):

- Reclaim: `reclaim_score` (binary; high weight)
- Stretch: close vs `bb_lower` (oversold context; only meaningful with reclaim)
- Capitulation proxy: volume vs estimated average shares (existing weak engine concept)

**Rule-level gate:** If `reclaim_score == 0`, cap actionability_score to ≤ 0.50 (so it cannot earn ⚡).

---

## 6) Tag semantics (UI stays universal)

The web currently displays:

- 🏆 if `leadership_score >= 0.90`
- ⚡ if `actionability_score >= 0.58`
- 👀 if `0.50 <= actionability_score < 0.58`

This stays unchanged; we change only how weak engine computes the two scores so that 🏆/⚡ remain meaningful.

---

## 7) Tracker policy (weak engine)

Goal: tracker is a research table of “top-ranked, high-conviction” candidates.

Proposed v1 rule:

- eligible if `engine == "weak"`
- rank <= 10
- must have 🏆 and ⚡ (i.e., leadership_score and actionability_score exceed thresholds)
- store `playbook_id` / `playbook_label` to analyze performance by playbook

---

## 8) Risk architecture (v1 guidance)

### Defensive RS / Leader Pullback
- stop: ~2.0 * ATR14 below entry reference (or below recent swing low)
- exits: scale partial at +1R, trail remainder under SMA20 or EMA21

### Capitulation → Reclaim
- stop: tight; below recent low or ~1.0–1.25 * ATR14
- exits: take partial fast (0.75R–1R), remainder into SMA20 / BB mid mean-reversion

---

## 9) Validation plan (v1)

- Compare weak engine v1 vs current weak engine (A/B)
- Ablations:
  - with/without reclaim_score gate
  - with/without atr_pct penalty
  - beta-neutral vs max_beta cap
- Metrics:
  - tail loss control (max drawdown per signal)
  - MAE distribution
  - expectancy per playbook

---

## 10) Implementation note (keep it simple)

v1 should use **existing indicator fields** (RS-vs-SPY can be Phase 2). The biggest immediate improvement in weak markets comes from:

1) reclaim_score gating for ⚡
2) atr_pct safety penalty
3) beta filter correction

This is enough to be logically sound and tradeable, without overengineering.
