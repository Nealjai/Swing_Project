from __future__ import annotations

from typing import Dict, List


def bull_candidates(
    rows: List[Dict],
    min_price: float,
    min_market_cap: float,
    min_beta_1y: float,
    min_volume: float,
) -> List[Dict]:
    candidates: List[Dict] = []
    for row in rows:
        close = row.get("close")
        high_20d = row.get("high_20d")
        rsi14 = row.get("rsi14")
        avg_dv = row.get("avg_dollar_volume_20d")
        volume = row.get("volume")
        market_cap = row.get("market_cap")
        beta_1y = row.get("beta_1y")

        if close is None or high_20d is None or rsi14 is None or avg_dv is None:
            continue
        if volume is None or market_cap is None or beta_1y is None:
            continue
        if close <= min_price or market_cap <= min_market_cap or beta_1y <= min_beta_1y or volume < min_volume:
            continue

        breakout = close / high_20d if high_20d > 0 else 0.0
        momentum = max(0.0, min(1.0, (rsi14 - 40.0) / 40.0))
        liquidity = min(1.0, avg_dv / 50_000_000.0)

        score = (0.5 * breakout) + (0.3 * momentum) + (0.2 * liquidity)
        if close >= high_20d * 0.995:
            reasons = [
                f"New/near 20D high: close={close:.2f}, high_20d={high_20d:.2f}",
                f"Momentum confirmation: RSI14={rsi14:.2f}",
                f"Liquidity filter passed: avg$vol20d={avg_dv:.0f}",
            ]
            candidates.append(
                {
                    **row,
                    "engine": "bull",
                    "score": float(score),
                    "score_breakdown": {
                        "breakout": float(breakout),
                        "momentum": float(momentum),
                        "liquidity": float(liquidity),
                    },
                    "reasons": reasons,
                    "signals": reasons,
                }
            )

    return candidates
