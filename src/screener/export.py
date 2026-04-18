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
    strategy: Dict | None = None,
    chart_data: Dict | None = None,
) -> None:
    scanner_settings = {
        "benchmark_symbol": settings_snapshot.get("benchmark_symbol"),
        "min_price": settings_snapshot.get("min_price"),
        "min_market_cap": settings_snapshot.get("min_market_cap"),
        "min_beta_1y": settings_snapshot.get("min_beta_1y"),
        "min_volume": settings_snapshot.get("min_volume"),
        "min_avg_dollar_volume_20d": settings_snapshot.get("min_avg_dollar_volume_20d"),
        "sma_regime_length": settings_snapshot.get("sma_regime_length"),
        "breakout_lookback": settings_snapshot.get("breakout_lookback"),
        "rsi_length": settings_snapshot.get("rsi_length"),
        "bb_length": settings_snapshot.get("bb_length"),
        "bb_std": settings_snapshot.get("bb_std"),
        "weak_rsi_threshold": settings_snapshot.get("weak_rsi_threshold"),
        "max_candidates": settings_snapshot.get("max_candidates"),
    }

    default_strategy = {
        "name": "US Market Regime Dual-Engine Screener",
        "summary": "Daily US stock scanner that switches between breakout and oversold-rebound engines based on SPY vs SMA200.",
        "market_regime_logic": {
            "benchmark": benchmark.get("symbol", "SPY"),
            "rule": f"Bull if close > SMA{scanner_settings.get('sma_regime_length', 200)}, else weak",
        },
        "engines": {
            "bull": {
                "title": "Bull: Breakout Momentum Engine",
                "rules": [
                    f"Close near/new {scanner_settings.get('breakout_lookback', 20)}D high",
                    "Momentum confirmation from RSI14",
                    "Liquidity filter and minimum price must pass",
                ],
                "take_profit": "Take profit: resistance_level + 1x ATR14 (fallback close + 3x ATR14)",
                "stop_loss": "Stop loss: bb_lower - 1x ATR14",
            },
            "weak": {
                "title": "Weak: Oversold Rebound Engine",
                "rules": [
                    f"RSI14 <= {scanner_settings.get('weak_rsi_threshold', 30)}",
                    "Close below lower Bollinger Band",
                    "Liquidity filter and minimum price must pass",
                ],
                "take_profit": "Take profit: resistance_level + 1x ATR14 (fallback close + 3x ATR14)",
                "stop_loss": "Stop loss: bb_lower - 1x ATR14",
            },
        },
        "fundamental_checklist": [
            "Dividend Yield (income support in weak tape)",
            "P/E ratio (avoid extreme overvaluation)",
            "P/B ratio (asset valuation context)",
            "ROE (quality and capital efficiency)",
            "Revenue/EPS growth and balance-sheet debt trend",
        ],
        "risk_notice": "Signals are for research only, not investment advice. Enforce stop-loss and position sizing discipline.",
    }

    payload = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "regime": regime,
            "engine": engine,
            "universe_size": universe_size,
            "candidate_count": len(candidates),
            "settings": settings_snapshot,
        },
        "benchmark": benchmark,
        "strategy": strategy or default_strategy,
        "scanner_settings": scanner_settings,
        "candidates": candidates,
        "diagnostics": diagnostics,
        "charts": chart_data or {},
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
