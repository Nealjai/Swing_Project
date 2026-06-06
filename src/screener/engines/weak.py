from __future__ import annotations

from typing import Dict, List

from .scoring import robust_unit_score, to_float


PLAYBOOK_DEF_RS = "DEF_RS"
PLAYBOOK_CAP_RECLAIM = "CAP_RECLAIM"
PLAYBOOK_LEADER_PB = "LEADER_PB"

PLAYBOOK_LABELS = {
    PLAYBOOK_DEF_RS: "Defensive Relative Strength",
    PLAYBOOK_CAP_RECLAIM: "Capitulation Reclaim",
    PLAYBOOK_LEADER_PB: "Leader Pullback",
}


def _playbook_for_row(
    oversold_raw: float | None,
    reclaim_score: float,
    trend200_raw: float | None,
    trend50_raw: float | None,
    sma20_distance_abs: float | None,
) -> str:
    oversold = bool(oversold_raw is not None and oversold_raw > 0.10)
    trend_healthy = bool(
        trend200_raw is not None
        and trend200_raw > 0.0
        and trend50_raw is not None
        and trend50_raw > 0.0
    )
    near_support = bool(sma20_distance_abs is not None and sma20_distance_abs <= 0.04)

    if oversold and reclaim_score >= 1.0:
        return PLAYBOOK_CAP_RECLAIM
    if trend_healthy and near_support:
        return PLAYBOOK_LEADER_PB
    return PLAYBOOK_DEF_RS


def weak_candidates(
    rows: List[Dict],
    min_price: float,
    min_market_cap: float,
    min_beta_1y: float,
    min_volume: float,
    weak_rsi_threshold: float,
    min_avg_dollar_volume_20d: float = 0.0,
) -> List[Dict]:
    candidates: List[Dict] = []

    prepared: List[Dict] = []
    for row in rows:
        close = to_float(row.get("close"))
        bb_lower = to_float(row.get("bb_lower"))
        rsi14 = to_float(row.get("rsi14"))
        avg_dv = to_float(row.get("avg_dollar_volume_20d"))
        volume = to_float(row.get("volume"))
        market_cap = to_float(row.get("market_cap"))

        sma200 = to_float(row.get("sma200"))
        sma50 = to_float(row.get("sma50"))
        sma20 = to_float(row.get("sma20"))
        ema9 = to_float(row.get("ema9"))
        atr14 = to_float(row.get("atr14"))

        if close is None or rsi14 is None or avg_dv is None:
            continue
        if volume is None or market_cap is None:
            continue
        if (
            close <= min_price
            or market_cap <= min_market_cap
            or volume < min_volume
            or avg_dv < min_avg_dollar_volume_20d
        ):
            continue

        # Legacy score retained for diagnostics comparison.
        reversal_quality_legacy = max(0.0, min(1.0, (weak_rsi_threshold - rsi14) / weak_rsi_threshold))
        extension_legacy = max(0.0, min(1.0, (bb_lower - close) / bb_lower)) if bb_lower not in (None, 0.0) else 0.0
        liquidity_legacy = min(1.0, avg_dv / 50_000_000.0)
        legacy_score = (0.5 * reversal_quality_legacy) + (0.3 * extension_legacy) + (0.2 * liquidity_legacy)

        avg_volume_shares = (avg_dv / close) if close > 0 else None
        capitulation_raw = (volume / avg_volume_shares) if avg_volume_shares not in (None, 0.0) else None

        oversold_raw = ((weak_rsi_threshold - rsi14) / weak_rsi_threshold) if weak_rsi_threshold > 0 else None
        extension_raw = ((bb_lower - close) / bb_lower) if bb_lower not in (None, 0.0) else None

        trend200_raw = ((close / sma200) - 1.0) if sma200 not in (None, 0.0) else None
        trend50_raw = ((close / sma50) - 1.0) if sma50 not in (None, 0.0) else None

        atr_pct_raw = (atr14 / close) if atr14 not in (None, 0.0) and close > 0 else None
        sma20_distance_abs = abs((close / sma20) - 1.0) if sma20 not in (None, 0.0) else None

        reclaim_bb = 1.0 if bb_lower not in (None, 0.0) and close > bb_lower else 0.0
        reclaim_ema = 1.0 if ema9 not in (None, 0.0) and close > ema9 else 0.0
        reclaim_sma20 = 1.0 if sma20 not in (None, 0.0) and close > sma20 else 0.0
        reclaim_score = max(reclaim_bb, reclaim_ema, reclaim_sma20)

        playbook_id = _playbook_for_row(
            oversold_raw=oversold_raw,
            reclaim_score=reclaim_score,
            trend200_raw=trend200_raw,
            trend50_raw=trend50_raw,
            sma20_distance_abs=sma20_distance_abs,
        )

        prepared.append(
            {
                "row": row,
                "legacy_score": float(legacy_score),
                "legacy_breakdown": {
                    "reversal_quality": float(reversal_quality_legacy),
                    "extension": float(extension_legacy),
                    "liquidity": float(liquidity_legacy),
                },
                "playbook_id": playbook_id,
                "reclaim_score": float(reclaim_score),
                "raw_features": {
                    "oversold": oversold_raw,
                    "extension": extension_raw,
                    "capitulation": capitulation_raw,
                    "trend200": trend200_raw,
                    "trend50": trend50_raw,
                    "liquidity": avg_dv,
                    "atr_pct": atr_pct_raw,
                    "sma20_distance_abs": sma20_distance_abs,
                },
            }
        )

    oversold_pop = [x["raw_features"]["oversold"] for x in prepared]
    extension_pop = [x["raw_features"]["extension"] for x in prepared]
    capitulation_pop = [x["raw_features"]["capitulation"] for x in prepared]

    trend200_pop = [x["raw_features"]["trend200"] for x in prepared]
    trend50_pop = [x["raw_features"]["trend50"] for x in prepared]
    liquidity_pop = [x["raw_features"]["liquidity"] for x in prepared]

    atr_pct_pop = [x["raw_features"]["atr_pct"] for x in prepared]
    support_dist_pop = [x["raw_features"]["sma20_distance_abs"] for x in prepared]

    for item in prepared:
        raw = item["raw_features"]
        playbook_id = str(item["playbook_id"])
        playbook_label = PLAYBOOK_LABELS.get(playbook_id, "Unknown")

        oversold_component = robust_unit_score(raw["oversold"], oversold_pop)
        extension_component = robust_unit_score(raw["extension"], extension_pop)
        capitulation_component = robust_unit_score(raw["capitulation"], capitulation_pop)

        trend200_component = robust_unit_score(raw["trend200"], trend200_pop)
        trend50_component = robust_unit_score(raw["trend50"], trend50_pop)
        liquidity_component = robust_unit_score(raw["liquidity"], liquidity_pop)

        safety_component = robust_unit_score(raw["atr_pct"], atr_pct_pop, invert=True)
        pullback_component = robust_unit_score(raw["sma20_distance_abs"], support_dist_pop, invert=True)

        reclaim_component = float(item["reclaim_score"])

        if playbook_id == PLAYBOOK_CAP_RECLAIM:
            actionability_score = (
                (0.45 * reclaim_component)
                + (0.25 * oversold_component)
                + (0.15 * extension_component)
                + (0.15 * capitulation_component)
            )
            leadership_score = (
                (0.20 * trend200_component)
                + (0.30 * liquidity_component)
                + (0.50 * safety_component)
            )
        elif playbook_id == PLAYBOOK_LEADER_PB:
            actionability_score = (
                (0.45 * reclaim_component)
                + (0.35 * pullback_component)
                + (0.20 * safety_component)
            )
            leadership_score = (
                (0.50 * trend200_component)
                + (0.20 * trend50_component)
                + (0.15 * liquidity_component)
                + (0.15 * safety_component)
            )
        else:
            actionability_score = (
                (0.35 * reclaim_component)
                + (0.35 * pullback_component)
                + (0.15 * extension_component)
                + (0.15 * safety_component)
            )
            leadership_score = (
                (0.40 * trend200_component)
                + (0.20 * trend50_component)
                + (0.20 * liquidity_component)
                + (0.20 * safety_component)
            )

        if reclaim_component < 1.0:
            actionability_score = min(actionability_score, 0.50)

        score = 100.0 * ((0.60 * actionability_score) + (0.40 * leadership_score))

        if leadership_score >= 0.70 and actionability_score >= 0.70:
            setup_tag = "Both"
        elif actionability_score >= 0.70:
            setup_tag = "Actionable Breakout"
        elif leadership_score >= 0.70:
            setup_tag = "Leadership"
        else:
            setup_tag = "Watchlist"

        intent = "trade" if (leadership_score >= 0.90 and actionability_score >= 0.58) else "watchlist"
        regime_reason = (
            "weak_engine_trade_requires_trophy_and_lightning"
            if intent == "trade"
            else "weak_engine_watchlist_wait_for_quality_or_reclaim"
        )

        reasons = [
            f"Playbook: {playbook_label}",
            f"Setup tag: {setup_tag}",
            f"Intent: {intent} ({regime_reason})",
            f"Actionability={actionability_score:.3f} (reclaim={reclaim_component:.3f}, oversold={oversold_component:.3f}, extension={extension_component:.3f}, capitulation={capitulation_component:.3f}, pullback={pullback_component:.3f})",
            f"Leadership={leadership_score:.3f} (trend200={trend200_component:.3f}, trend50={trend50_component:.3f}, liquidity={liquidity_component:.3f}, safety={safety_component:.3f})",
            f"Legacy score={item['legacy_score']:.3f} kept in debug for comparison",
        ]

        funnel = {
            "stages": [
                {
                    "name": "hard_filters",
                    "passed": True,
                    "checks": {
                        "min_price": True,
                        "min_market_cap": True,
                        "min_volume": True,
                        "min_avg_dollar_volume_20d": True,
                        "beta_filter_disabled_for_weak_engine": True,
                    },
                },
                {
                    "name": "playbook_selection",
                    "passed": True,
                    "checks": {
                        "playbook_id": playbook_id,
                        "playbook_label": playbook_label,
                        "reclaim_score": reclaim_component,
                    },
                },
                {
                    "name": "normalized_scoring",
                    "passed": True,
                    "checks": {
                        "leadership_score": float(leadership_score),
                        "actionability_score": float(actionability_score),
                        "score": float(score),
                        "setup_tag": setup_tag,
                        "intent": intent,
                    },
                },
            ],
            "snapshots": {
                "raw_features": {
                    "oversold": raw["oversold"],
                    "extension": raw["extension"],
                    "capitulation": raw["capitulation"],
                    "trend200": raw["trend200"],
                    "trend50": raw["trend50"],
                    "liquidity": raw["liquidity"],
                    "atr_pct": raw["atr_pct"],
                    "sma20_distance_abs": raw["sma20_distance_abs"],
                    "reclaim_score": reclaim_component,
                },
                "normalized_components": {
                    "oversold_component": float(oversold_component),
                    "extension_component": float(extension_component),
                    "capitulation_component": float(capitulation_component),
                    "trend200_component": float(trend200_component),
                    "trend50_component": float(trend50_component),
                    "liquidity_component": float(liquidity_component),
                    "safety_component": float(safety_component),
                    "pullback_component": float(pullback_component),
                    "reclaim_component": float(reclaim_component),
                },
            },
            "reasons": reasons,
        }

        candidates.append(
            {
                **item["row"],
                "engine": "weak",
                "score": float(score),
                "playbook_id": playbook_id,
                "playbook_label": playbook_label,
                "intent": intent,
                "regime_reason": regime_reason,
                "setup_tag": setup_tag,
                "leadership_score": float(leadership_score),
                "actionability_score": float(actionability_score),
                "score_breakdown": {
                    "leadership_score": float(leadership_score),
                    "actionability_score": float(actionability_score),
                    "oversold_component": float(oversold_component),
                    "extension_component": float(extension_component),
                    "capitulation_component": float(capitulation_component),
                    "trend200_component": float(trend200_component),
                    "trend50_component": float(trend50_component),
                    "liquidity_component": float(liquidity_component),
                    "safety_component": float(safety_component),
                    "pullback_component": float(pullback_component),
                    "reclaim_component": float(reclaim_component),
                },
                "debug_metrics": {
                    "legacy_score": float(item["legacy_score"]),
                    "legacy_breakdown": item["legacy_breakdown"],
                    "raw_features": raw,
                    "reclaim_score": float(reclaim_component),
                },
                "funnel": funnel,
                "reasons": reasons,
                "signals": reasons,
            }
        )

    candidates.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
    return candidates
