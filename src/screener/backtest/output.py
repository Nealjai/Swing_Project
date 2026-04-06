from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import pandas as pd


def write_trade_log(trades: pd.DataFrame, out_dir: str = "data/backtests") -> Path:
    target_dir = Path(out_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    path = target_dir / f"trades_{ts}.csv"
    trades.to_csv(path, index=False)
    return path


def write_summary_json(payload: Dict[str, object], path: str = "docs/data/backtest_summary.json") -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def format_summary_table(summary: Dict[str, object]) -> str:
    overall = (summary.get("stats") or {}).get("overall") or {}
    by_engine = (summary.get("stats") or {}).get("by_engine") or {}

    def _line(label: str, stats: Dict[str, object]) -> str:
        return (
            f"{label:<9} | trades={int(stats.get('total_trades', 0)):>4} "
            f"| win_rate={str(stats.get('win_rate')):>6} "
            f"| expectancy={str(stats.get('expectancy_pct')):>8} "
            f"| pf={str(stats.get('profit_factor')):>8} "
            f"| avg_hold={str(stats.get('avg_hold_days')):>6}"
        )

    lines = [
        "Backtest Summary",
        "---------------------------------------------------------------",
        _line("Overall", overall),
        _line("Bull", by_engine.get("Bull") or {}),
        _line("Weak", by_engine.get("Weak") or {}),
        _line("Combined", by_engine.get("Combined") or {}),
    ]
    return "\n".join(lines)


def build_summary_payload(
    *,
    engine: str,
    start_date: str,
    end_date: str,
    symbol_mode: str,
    symbol_count: int,
    benchmark_symbol: str,
    stats: Dict[str, object],
    diagnostics: Dict[str, object],
    trades_path: Path,
    portfolio: Dict[str, object] | None = None,
    methodology: Dict[str, object] | None = None,
) -> Dict[str, object]:
    payload: Dict[str, object] = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "engine": engine,
            "start_date": start_date,
            "end_date": end_date,
            "symbol_mode": symbol_mode,
            "symbol_count": symbol_count,
            "benchmark_symbol": benchmark_symbol,
            "trade_log_csv": str(trades_path).replace("\\", "/"),
        },
        "stats": stats,
        "diagnostics": diagnostics,
    }
    if portfolio:
        payload["portfolio"] = portfolio
    if methodology:
        meta = payload.get("meta")
        if isinstance(meta, dict):
            meta.update(methodology)
    return payload
