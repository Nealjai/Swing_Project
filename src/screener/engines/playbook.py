from __future__ import annotations

import math
from collections import Counter
from typing import Dict, List, Tuple


PLAYBOOK_BREAKOUT = "BREAKOUT"
PLAYBOOK_PULLBACK_ENTRY = "PULLBACK_ENTRY"
PLAYBOOK_TIGHT_BASE = "TIGHT_BASE"
PLAYBOOK_CAPITULATION_RECLAIM = "CAPITULATION_RECLAIM"
PLAYBOOK_LEADER_PULLBACK = "LEADER_PULLBACK"
PLAYBOOK_DEFENSIVE_RS = "DEFENSIVE_RS"
PLAYBOOK_MISC = "MISC"


def _to_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:  # noqa: BLE001
        return None


def _infer_playbook_id(candidate: Dict) -> str:
    engine = str(candidate.get("engine") or "").strip().lower()

    if engine == "bull":
        stage = str(candidate.get("pattern_stage") or "").strip().lower()
        if stage in {"pullback-entry-ready", "post-breakout-watch"}:
            return PLAYBOOK_PULLBACK_ENTRY
        if stage == "breakout":
            return PLAYBOOK_BREAKOUT
        if stage in {"near-pivot", "early-stage"}:
            return PLAYBOOK_TIGHT_BASE
        return PLAYBOOK_MISC

    if engine == "weak":
        weak_pb = str(candidate.get("playbook_id") or "").strip().upper()
        if weak_pb == "CAP_RECLAIM":
            return PLAYBOOK_CAPITULATION_RECLAIM
        if weak_pb == "LEADER_PB":
            return PLAYBOOK_LEADER_PULLBACK
        if weak_pb == "DEF_RS":
            return PLAYBOOK_DEFENSIVE_RS
        return PLAYBOOK_MISC

    return PLAYBOOK_MISC


def _allowed_in_regime(playbook_id: str, regime_label: str) -> bool:
    regime = str(regime_label or "Bull").strip().capitalize()

    allowed = {
        "Bull": {
            PLAYBOOK_BREAKOUT,
            PLAYBOOK_PULLBACK_ENTRY,
            PLAYBOOK_TIGHT_BASE,
            PLAYBOOK_LEADER_PULLBACK,
            PLAYBOOK_CAPITULATION_RECLAIM,
        },
        "Choppy": {
            PLAYBOOK_PULLBACK_ENTRY,
            PLAYBOOK_LEADER_PULLBACK,
            PLAYBOOK_CAPITULATION_RECLAIM,
            PLAYBOOK_DEFENSIVE_RS,
        },
        "Bear": {
            PLAYBOOK_CAPITULATION_RECLAIM,
            PLAYBOOK_DEFENSIVE_RS,
        },
    }
    return playbook_id in allowed.get(regime, set())


def _regime_liquidity_floor(
    regime_label: str,
    *,
    min_avg_dollar_volume_20d: float,
    min_avg_dollar_volume_20d_bull: float,
    min_avg_dollar_volume_20d_choppy: float,
    min_avg_dollar_volume_20d_bear: float,
) -> float:
    regime = str(regime_label or "Bull").strip().capitalize()
    if regime == "Bear":
        return float(max(min_avg_dollar_volume_20d, min_avg_dollar_volume_20d_bear))
    if regime == "Choppy":
        return float(max(min_avg_dollar_volume_20d, min_avg_dollar_volume_20d_choppy))
    return float(max(min_avg_dollar_volume_20d, min_avg_dollar_volume_20d_bull))


def _tiered_max_atr_pct(
    close: float,
    *,
    atr_pct_tier_lt_20: float,
    atr_pct_tier_20_to_100: float,
    atr_pct_tier_gt_100: float,
) -> float:
    if close < 20.0:
        return float(atr_pct_tier_lt_20)
    if close <= 100.0:
        return float(atr_pct_tier_20_to_100)
    return float(atr_pct_tier_gt_100)


def _absolute_quality_gate(
    candidate: Dict,
    *,
    regime_label: str,
    playbook_id: str,
    min_price: float,
    min_avg_dollar_volume_20d: float,
    min_avg_dollar_volume_20d_bull: float,
    min_avg_dollar_volume_20d_choppy: float,
    min_avg_dollar_volume_20d_bear: float,
    min_atr_dollars: float,
    atr_pct_tier_lt_20: float,
    atr_pct_tier_20_to_100: float,
    atr_pct_tier_gt_100: float,
    max_atr_pct: float,
) -> Tuple[bool, str]:
    close = _to_float(candidate.get("close"))
    avg_dv = _to_float(candidate.get("avg_dollar_volume_20d"))
    median_dv = _to_float(candidate.get("median_dollar_volume_20d"))
    atr14 = _to_float(candidate.get("atr14"))

    if close is None or close <= min_price:
        return False, "failed_min_price"

    regime_floor = _regime_liquidity_floor(
        regime_label,
        min_avg_dollar_volume_20d=min_avg_dollar_volume_20d,
        min_avg_dollar_volume_20d_bull=min_avg_dollar_volume_20d_bull,
        min_avg_dollar_volume_20d_choppy=min_avg_dollar_volume_20d_choppy,
        min_avg_dollar_volume_20d_bear=min_avg_dollar_volume_20d_bear,
    )
    if avg_dv is None or avg_dv < regime_floor:
        return False, "failed_regime_min_avg_dollar_volume_20d"
    if median_dv is None or median_dv < regime_floor:
        return False, "failed_median_dollar_volume_20d_stability"

    if atr14 is None or atr14 < min_atr_dollars:
        return False, "failed_min_atr_dollars"

    atr_pct = (atr14 / close) if close > 0 else None
    tiered_max_atr_pct = _tiered_max_atr_pct(
        close,
        atr_pct_tier_lt_20=atr_pct_tier_lt_20,
        atr_pct_tier_20_to_100=atr_pct_tier_20_to_100,
        atr_pct_tier_gt_100=atr_pct_tier_gt_100,
    )
    if atr_pct is not None and atr_pct > tiered_max_atr_pct:
        return False, "failed_tiered_max_atr_pct"
    if atr_pct is not None and atr_pct > max_atr_pct:
        return False, "failed_max_atr_pct"

    leadership = _to_float(candidate.get("leadership_score")) or 0.0
    actionability = _to_float(candidate.get("actionability_score")) or 0.0

    if playbook_id == PLAYBOOK_BREAKOUT:
        if leadership < 0.65 or actionability < 0.68:
            return False, "failed_breakout_quality"
        if str(candidate.get("breakout_state") or "") not in {"breakout", "post_breakout_watch"}:
            return False, "failed_breakout_state"
        return True, "passed"

    if playbook_id == PLAYBOOK_PULLBACK_ENTRY:
        if leadership < 0.62 or actionability < 0.60:
            return False, "failed_pullback_quality"
        if str(candidate.get("pullback_entry_state") or "") not in {
            "pullback-entry-ready",
            "post-breakout-watch",
        }:
            return False, "failed_pullback_state"
        return True, "passed"

    if playbook_id == PLAYBOOK_TIGHT_BASE:
        if leadership < 0.68 or actionability < 0.56:
            return False, "failed_tight_base_quality"
        pivot_distance = _to_float(candidate.get("pivot_distance_pct"))
        if pivot_distance is not None and pivot_distance > 0.04:
            return False, "failed_tight_base_distance"
        return True, "passed"

    if playbook_id == PLAYBOOK_CAPITULATION_RECLAIM:
        score_breakdown = candidate.get("score_breakdown") if isinstance(candidate.get("score_breakdown"), dict) else {}
        reclaim_component = _to_float(score_breakdown.get("reclaim_component"))
        if reclaim_component is not None and reclaim_component < 1.0:
            return False, "failed_reclaim_confirmation"
        if actionability < 0.58:
            return False, "failed_reclaim_actionability"
        return True, "passed"

    if playbook_id == PLAYBOOK_LEADER_PULLBACK:
        if leadership < 0.66 or actionability < 0.56:
            return False, "failed_leader_pullback_quality"
        return True, "passed"

    if playbook_id == PLAYBOOK_DEFENSIVE_RS:
        if leadership < 0.72:
            return False, "failed_defensive_rs_quality"
        return True, "passed"

    if leadership < 0.70 or actionability < 0.60:
        return False, "failed_generic_quality"

    return True, "passed"


def select_playbook_candidates(
    candidates: List[Dict],
    *,
    regime_label: str,
    min_price: float,
    min_avg_dollar_volume_20d: float,
    max_atr_pct: float,
    min_avg_dollar_volume_20d_bull: float = 30_000_000.0,
    min_avg_dollar_volume_20d_choppy: float = 75_000_000.0,
    min_avg_dollar_volume_20d_bear: float = 100_000_000.0,
    min_atr_dollars: float = 0.50,
    atr_pct_tier_lt_20: float = 0.12,
    atr_pct_tier_20_to_100: float = 0.10,
    atr_pct_tier_gt_100: float = 0.08,
) -> Tuple[List[Dict], Dict]:
    regime = str(regime_label or "Bull").strip().capitalize()

    selected: List[Dict] = []
    playbook_counter: Counter[str] = Counter()

    rejected_gate = 0
    rejected_regime = 0
    trade_count = 0
    watchlist_count = 0

    for candidate in candidates:
        row = dict(candidate)
        playbook_id = _infer_playbook_id(row)
        playbook_counter[playbook_id] += 1

        passed_gate, gate_reason = _absolute_quality_gate(
            row,
            regime_label=regime,
            playbook_id=playbook_id,
            min_price=min_price,
            min_avg_dollar_volume_20d=min_avg_dollar_volume_20d,
            min_avg_dollar_volume_20d_bull=min_avg_dollar_volume_20d_bull,
            min_avg_dollar_volume_20d_choppy=min_avg_dollar_volume_20d_choppy,
            min_avg_dollar_volume_20d_bear=min_avg_dollar_volume_20d_bear,
            min_atr_dollars=min_atr_dollars,
            atr_pct_tier_lt_20=atr_pct_tier_lt_20,
            atr_pct_tier_20_to_100=atr_pct_tier_20_to_100,
            atr_pct_tier_gt_100=atr_pct_tier_gt_100,
            max_atr_pct=max_atr_pct,
        )
        if not passed_gate:
            rejected_gate += 1
            continue

        allowed = _allowed_in_regime(playbook_id, regime)
        intent = "trade" if allowed else "watchlist"
        if not allowed:
            rejected_regime += 1

        if intent == "trade":
            trade_count += 1
        else:
            watchlist_count += 1

        reasons = list(row.get("reasons") or [])
        reasons.append(f"Playbook-first routing: {playbook_id}")
        reasons.append(f"Absolute gate: {gate_reason}")
        reasons.append(f"Regime permissioning: {'allowed' if allowed else 'watchlist_only'} ({regime})")

        row["playbook_id"] = playbook_id
        row["intent"] = intent
        row["regime_label"] = regime
        row["reasons"] = reasons
        row["signals"] = reasons
        selected.append(row)

    selected.sort(key=lambda x: float(_to_float(x.get("score")) or 0.0), reverse=True)

    trade_allowed = trade_count > 0
    if trade_allowed:
        cash_reason = "qualified_trade_setups_available"
    elif len(selected) > 0:
        cash_reason = "watchlist_only_no_regime_permitted_trade"
    else:
        cash_reason = "no_candidates_passed_absolute_gates"

    policy = {
        "trade_allowed": trade_allowed,
        "cash_reason": cash_reason,
        "qualified_trade_count": int(trade_count),
        "watchlist_count": int(watchlist_count),
        "rejected_by_absolute_gate": int(rejected_gate),
        "watchlist_for_regime_count": int(rejected_regime),
        "playbook_distribution": dict(playbook_counter),
        "liquidity_policy": {
            "regime": regime,
            "min_avg_dollar_volume_20d": _regime_liquidity_floor(
                regime,
                min_avg_dollar_volume_20d=min_avg_dollar_volume_20d,
                min_avg_dollar_volume_20d_bull=min_avg_dollar_volume_20d_bull,
                min_avg_dollar_volume_20d_choppy=min_avg_dollar_volume_20d_choppy,
                min_avg_dollar_volume_20d_bear=min_avg_dollar_volume_20d_bear,
            ),
            "stability_rule": "median_dollar_volume_20d >= regime_floor",
        },
        "volatility_policy": {
            "min_atr_dollars": float(min_atr_dollars),
            "atr_pct_tiers": {
                "lt_20": float(atr_pct_tier_lt_20),
                "between_20_and_100": float(atr_pct_tier_20_to_100),
                "gt_100": float(atr_pct_tier_gt_100),
            },
            "global_max_atr_pct": float(max_atr_pct),
        },
    }

    return selected, policy
