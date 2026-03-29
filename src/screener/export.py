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
