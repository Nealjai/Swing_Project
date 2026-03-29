from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd


def _sanitize(value):
    if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
        return None
    return value


def _sanitize_dict(d: Dict) -> Dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out[k] = _sanitize_dict(v)
        elif isinstance(v, list):
            out[k] = [_sanitize_dict(x) if isinstance(x, dict) else _sanitize(x) for x in v]
        else:
            out[k] = _sanitize(v)
    return out


def export_outputs(
    settings_snapshot: Dict,
    benchmark: Dict,
    candidates: List[Dict],
    diagnostics: Dict,
    regime: str,
    engine: str,
    universe_size: int,
    json_path: str,
    csv_path: str,
) -> None:
    benchmark_symbol = settings_snapshot.get("benchmark_symbol", "SPY")
    sma_len = settings_snapshot.get("sma_regime_length", 200)
    breakout_lookback = settings_snapshot.get("breakout_lookback", 20)
    weak_rsi_threshold = settings_snapshot.get("weak_rsi_threshold", 30)

    regime_rule = (
        f"Regime rule: {benchmark_symbol} close vs SMA{sma_len}. "
        "Above = bull engine, otherwise weak engine."
    )
    bull_rule = f"Bull engine signal: close within 0.5% of {breakout_lookback}-day high."
    weak_rule = f"Weak engine signal: close at/below lower Bollinger Band and RSI <= {weak_rsi_threshold}."
    bull_ranking = "Bull ranking factors: breakout (50%), momentum from RSI (30%), liquidity (20%)."
    weak_ranking = (
        "Weak ranking factors: reversal quality from RSI (50%), extension below lower band (30%), "
        "liquidity (20%)."
    )

    active_engine_name = "Bull Engine (Trend/Breakout)" if engine == "bull" else "Weak Engine (Oversold Rebound)"
    active_engine_summary = (
        "Bull regime detected. The trend/breakout engine is active."
        if engine == "bull"
        else "Weak regime detected. The oversold-rebound engine is active."
    )
    active_engine_logic = [
        regime_rule,
        "Filter: keep stocks above minimum price and minimum average dollar volume.",
        bull_rule if engine == "bull" else weak_rule,
        bull_ranking if engine == "bull" else weak_ranking,
    ]

    payload = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "regime": regime,
            "engine": engine,
            "universe_size": universe_size,
            "candidate_count": len(candidates),
            "settings": settings_snapshot,
            "strategy": {
                "active_engine_name": active_engine_name,
                "active_engine_summary": active_engine_summary,
                "active_engine_logic": active_engine_logic,
                "regime_rule": regime_rule,
                "bull_rule": bull_rule,
                "weak_rule": weak_rule,
                "bull_ranking": bull_ranking,
                "weak_ranking": weak_ranking,
                "selection_overview": [
                    regime_rule,
                    f"Bull rules (used only in bull regime): {bull_rule.replace('Bull engine signal: ', '')}",
                    f"Weak rules (used only in weak regime): {weak_rule.replace('Weak engine signal: ', '')}",
                    (
                        "Ranking is score-based inside the active engine. "
                        f"{bull_ranking if engine == 'bull' else weak_ranking}"
                    ),
                ],
            },
        },
        "benchmark": benchmark,
        "candidates": candidates,
        "diagnostics": diagnostics,
    }

    payload = _sanitize_dict(payload)

    jp = Path(json_path)
    cp = Path(csv_path)
    jp.parent.mkdir(parents=True, exist_ok=True)
    cp.parent.mkdir(parents=True, exist_ok=True)

    jp.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    flat_rows = []
    for row in candidates:
        score_breakdown = row.get("score_breakdown", {})
        flat = {k: v for k, v in row.items() if k != "score_breakdown"}
        for key, val in score_breakdown.items():
            flat[f"score_{key}"] = val
        flat_rows.append(flat)

    pd.DataFrame(flat_rows).to_csv(cp, index=False)
