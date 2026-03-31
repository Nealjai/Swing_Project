from __future__ import annotations

from typing import Dict, List


def weak_candidates(
    rows: List[Dict],
    min_price: float,
    min_avg_dollar_volume: float,
    weak_rsi_threshold: float,
) -> List[Dict]:
    candidates: List[Dict] = []
    for row in rows:
        close = row.get("close")
        bb_lower = row.get("bb_lower")
        rsi14 = row.get("rsi14")
        avg_dv = row.get("avg_dollar_volume_20d")

        if close is None or bb_lower is None or rsi14 is None or avg_dv is None:
            continue
        if close < min_price or avg_dv < min_avg_dollar_volume:
            continue

        below_bb = close <= bb_lower
        oversold = rsi14 <= weak_rsi_threshold
        if not (below_bb and oversold):
            continue

        reversal_quality = max(0.0, min(1.0, (weak_rsi_threshold - rsi14) / weak_rsi_threshold))
        extension = max(0.0, min(1.0, (bb_lower - close) / bb_lower)) if bb_lower > 0 else 0.0
        liquidity = min(1.0, avg_dv / 50_000_000.0)

        score = (0.5 * reversal_quality) + (0.3 * extension) + (0.2 * liquidity)

        reasons = [
            f"Oversold condition: RSI14={rsi14:.2f} <= {weak_rsi_threshold:.2f}",
            f"Below lower Bollinger Band: close={close:.2f}, bb_lower={bb_lower:.2f}",
            f"Liquidity filter passed: avg$vol20d={avg_dv:.0f}",
        ]

        candidates.append(
            {
                **row,
                "engine": "weak",
                "score": float(score),
                "score_breakdown": {
                    "reversal_quality": float(reversal_quality),
                    "extension": float(extension),
                    "liquidity": float(liquidity),
                },
                "reasons": reasons,
                "signals": reasons,
            }
        )

    return candidates
