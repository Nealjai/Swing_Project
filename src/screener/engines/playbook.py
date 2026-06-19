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


def _absolute_quality_gate(
    candidate: Dict,
    *,
    playbook_id: str,
    min_price: float,
    min_avg_dollar_volume_20d: float,
    max_atr_pct: float,
) -> Tuple[bool, str]:
    close = _to_float(candidate.get("close"))
    avg_dv = _to_float(candidate.get("avg_dollar_volume_20d"))
    atr14 = _to_float(candidate.get("atr14"))

    if close is None or close <= min_price:
        return False, "failed_min_price"
    if avg_dv is None or avg_dv < min_avg_dollar_volume_20d:
        return False, "failed_min_avg_dollar_volume_20d"

    atr_pct = (atr14 / close) if atr14 not in (None, 0.0) and close > 0 else None
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
            playbook_id=playbook_id,
            min_price=min_price,
            min_avg_dollar_volume_20d=min_avg_dollar_volume_20d,
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
    }

    return selected, policy
