from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List

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


def _safe_run_id(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raw = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return re.sub(r"[^A-Za-z0-9._-]+", "_", raw)


def write_run_config_json(
    run_config: Dict[str, object],
    *,
    run_id: str,
    out_dir: str = "docs/data/backtest_runs",
) -> Path:
    target_dir = Path(out_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_run_id = _safe_run_id(run_id)
    target = target_dir / f"run_config_{safe_run_id}.json"
    target.write_text(json.dumps(run_config, indent=2), encoding="utf-8")
    return target


def write_symbols_json(
    symbols: Iterable[str],
    *,
    run_id: str,
    out_dir: str = "docs/data/backtest_runs",
) -> Path:
    target_dir = Path(out_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_run_id = _safe_run_id(run_id)
    normalized = sorted({str(s).strip().upper() for s in symbols if str(s).strip()})
    target = target_dir / f"symbols_{safe_run_id}.json"
    target.write_text(json.dumps({"symbols": normalized}, indent=2), encoding="utf-8")
    return target


def write_summary_history_json(
    payload: Dict[str, object],
    *,
    run_id: str,
    out_dir: str = "docs/data/backtest_runs",
) -> Path:
    target_dir = Path(out_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_run_id = _safe_run_id(run_id)
    target = target_dir / f"backtest_summary_{safe_run_id}.json"
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def write_candidates_csv(
    candidates: pd.DataFrame,
    *,
    run_id: str,
    out_dir: str = "docs/data/backtest_runs",
) -> Path:
    target_dir = Path(out_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_run_id = _safe_run_id(run_id)
    path = target_dir / f"candidates_{safe_run_id}.csv"
    candidates.to_csv(path, index=False)
    return path


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
    benchmark: Dict[str, object] | None = None,
    methodology: Dict[str, object] | None = None,
    run_id: str | None = None,
    run_config: Dict[str, object] | None = None,
    symbols_path: str | None = None,
    summary_history_path: str | None = None,
    run_config_path: str | None = None,
    candidates_path: str | None = None,
) -> Dict[str, object]:
    payload: Dict[str, object] = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "run_name": (run_config or {}).get("run_name") if isinstance(run_config, dict) else None,
            "run_description": (run_config or {}).get("run_description") if isinstance(run_config, dict) else None,
            "engine": engine,
            "start_date": start_date,
            "end_date": end_date,
            "symbol_mode": symbol_mode,
            "symbol_count": symbol_count,
            "benchmark_symbol": benchmark_symbol,
            "trade_log_csv": str(trades_path).replace("\\", "/"),
            "symbols_json": symbols_path,
            "run_summary_json": summary_history_path,
            "run_config_json": run_config_path,
            "run_config": run_config,
            "candidates_csv": candidates_path,
        },
        "stats": stats,
        "diagnostics": diagnostics,
    }
    if portfolio:
        payload["portfolio"] = portfolio
    if benchmark:
        payload["benchmark"] = benchmark
    if methodology:
        meta = payload.get("meta")
        if isinstance(meta, dict):
            meta.update(methodology)
    return payload



def write_backtest_runs_index_json(
    *,
    out_dir: str = "docs/data/backtest_runs",
    file_name: str = "index.json",
) -> Path:
    target_dir = Path(out_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    entries: List[Dict[str, object]] = []
    for summary_path in sorted(target_dir.glob("backtest_summary_*.json")):
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue

        meta = payload.get("meta") if isinstance(payload, dict) else {}
        if not isinstance(meta, dict):
            meta = {}

        run_config = meta.get("run_config") if isinstance(meta.get("run_config"), dict) else {}
        date_range = run_config.get("date_range") if isinstance(run_config.get("date_range"), dict) else {}
        user_inputs = run_config.get("user_inputs") if isinstance(run_config.get("user_inputs"), dict) else {}

        start_date = date_range.get("start_date") or meta.get("start_date")
        end_date = date_range.get("end_date") or meta.get("end_date")
        initial_capital = user_inputs.get("initial_capital")
        max_positions = user_inputs.get("max_positions")

        entries.append(
            {
                "run_id": meta.get("run_id"),
                "generated_at": meta.get("generated_at"),
                "run_name": meta.get("run_name"),
                "run_description": meta.get("run_description"),
                "summary_path": str(summary_path).replace("\\", "/"),
                "engine": meta.get("engine") or run_config.get("engine"),
                "symbol_mode": meta.get("symbol_mode"),
                "symbol_count": meta.get("symbol_count"),
                "benchmark_symbol": meta.get("benchmark_symbol"),
                "start_date": start_date,
                "end_date": end_date,
                "initial_capital": initial_capital,
                "max_positions": max_positions,
                "has_benchmark": isinstance(payload.get("benchmark"), dict),
            }
        )

    entries.sort(key=lambda x: str(x.get("generated_at") or ""), reverse=True)

    index_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_count": len(entries),
        "runs": entries,
    }

    target = target_dir / file_name
    target.write_text(json.dumps(index_payload, indent=2), encoding="utf-8")
    return target
