from __future__ import annotations

from typing import Dict, List


def rank_candidates(candidates: List[Dict], max_candidates: int) -> List[Dict]:
    ordered = sorted(candidates, key=lambda x: x.get("score", 0.0), reverse=True)
    out: List[Dict] = []
    for idx, item in enumerate(ordered[:max_candidates], start=1):
        row = dict(item)
        row["rank"] = idx
        out.append(row)
    return out
