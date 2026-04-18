from __future__ import annotations

from typing import Dict, List

from .scoring import robust_unit_score, to_float


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
        beta_1y = to_float(row.get("beta_1y"))
        sma200 = to_float(row.get("sma200"))

        if close is None or bb_lower is None or rsi14 is None or avg_dv is None:
            continue
        if volume is None or market_cap is None or beta_1y is None:
            continue
        if (
            close <= min_price
            or market_cap <= min_market_cap
            or beta_1y <= min_beta_1y
            or volume < min_volume
            or avg_dv < min_avg_dollar_volume_20d
        ):
            continue

        # Legacy score for debug-only comparison.
        reversal_quality_legacy = max(0.0, min(1.0, (weak_rsi_threshold - rsi14) / weak_rsi_threshold))
        extension_legacy = max(0.0, min(1.0, (bb_lower - close) / bb_lower)) if bb_lower > 0 else 0.0
        liquidity_legacy = min(1.0, avg_dv / 50_000_000.0)
        legacy_score = (0.5 * reversal_quality_legacy) + (0.3 * extension_legacy) + (0.2 * liquidity_legacy)

        avg_volume_shares = (avg_dv / close) if close > 0 else None
        capitulation_raw = (volume / avg_volume_shares) if avg_volume_shares not in (None, 0.0) else None

        reversal_raw = ((weak_rsi_threshold - rsi14) / weak_rsi_threshold) if weak_rsi_threshold > 0 else None
        extension_raw = ((bb_lower - close) / bb_lower) if bb_lower > 0 else None
        trend_raw = ((close / sma200) - 1.0) if sma200 not in (None, 0.0) else None

        prepared.append(
            {
                "row": row,
                "legacy_score": float(legacy_score),
                "legacy_breakdown": {
                    "reversal_quality": float(reversal_quality_legacy),
                    "extension": float(extension_legacy),
                    "liquidity": float(liquidity_legacy),
                },
                "raw_features": {
                    "reversal": reversal_raw,
                    "extension": extension_raw,
                    "capitulation": capitulation_raw,
                    "trend": trend_raw,
                    "liquidity": avg_dv,
                },
            }
        )

    reversal_pop = [x["raw_features"]["reversal"] for x in prepared]
    extension_pop = [x["raw_features"]["extension"] for x in prepared]
    capitulation_pop = [x["raw_features"]["capitulation"] for x in prepared]
    trend_pop = [x["raw_features"]["trend"] for x in prepared]
    liquidity_pop = [x["raw_features"]["liquidity"] for x in prepared]

    for item in prepared:
        raw = item["raw_features"]

        reversal_component = robust_unit_score(raw["reversal"], reversal_pop)
        extension_component = robust_unit_score(raw["extension"], extension_pop)
        capitulation_component = robust_unit_score(raw["capitulation"], capitulation_pop)

        trend_component = robust_unit_score(raw["trend"], trend_pop)
        liquidity_component = robust_unit_score(raw["liquidity"], liquidity_pop)

        actionability_score = (0.45 * reversal_component) + (0.35 * extension_component) + (0.20 * capitulation_component)
        leadership_score = (0.70 * trend_component) + (0.30 * liquidity_component)
        score = 100.0 * ((0.60 * actionability_score) + (0.40 * leadership_score))

        if leadership_score >= 0.70 and actionability_score >= 0.70:
            setup_tag = "Both"
        elif actionability_score >= 0.70:
            setup_tag = "Actionable Breakout"
        elif leadership_score >= 0.70:
            setup_tag = "Leadership"
        else:
            setup_tag = "Watchlist"

        reasons = [
            f"Setup tag: {setup_tag}",
            f"Actionability={actionability_score:.3f} (reversal={reversal_component:.3f}, extension={extension_component:.3f}, capitulation={capitulation_component:.3f})",
            f"Leadership={leadership_score:.3f} (trend={trend_component:.3f}, liquidity={liquidity_component:.3f})",
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
                        "min_beta_1y": True,
                        "min_volume": True,
                        "min_avg_dollar_volume_20d": True,
                    },
                },
                {
                    "name": "reversal_context",
                    "passed": True,
                    "checks": {
                        "weak_rsi_threshold": float(weak_rsi_threshold),
                        "close_vs_bb_lower": raw["extension"],
                        "trend_vs_sma200": raw["trend"],
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
                    },
                },
            ],
            "snapshots": {
                "raw_features": {
                    "reversal": raw["reversal"],
                    "extension": raw["extension"],
                    "capitulation": raw["capitulation"],
                    "trend": raw["trend"],
                    "liquidity": raw["liquidity"],
                },
                "normalized_components": {
                    "reversal_component": float(reversal_component),
                    "extension_component": float(extension_component),
                    "capitulation_component": float(capitulation_component),
                    "trend_component": float(trend_component),
                    "liquidity_component": float(liquidity_component),
                },
            },
            "reasons": reasons,
        }

        candidates.append(
            {
                **item["row"],
                "engine": "weak",
                "score": float(score),
                "setup_tag": setup_tag,
                "leadership_score": float(leadership_score),
                "actionability_score": float(actionability_score),
                "score_breakdown": {
                    "leadership_score": float(leadership_score),
                    "actionability_score": float(actionability_score),
                    "reversal_component": float(reversal_component),
                    "extension_component": float(extension_component),
                    "capitulation_component": float(capitulation_component),
                    "trend_component": float(trend_component),
                    "liquidity_component": float(liquidity_component),
                },
                "debug_metrics": {
                    "legacy_score": float(item["legacy_score"]),
                    "legacy_breakdown": item["legacy_breakdown"],
                    "raw_features": raw,
                },
                "funnel": funnel,
                "reasons": reasons,
                "signals": reasons,
            }
        )

    candidates.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
    return candidates
