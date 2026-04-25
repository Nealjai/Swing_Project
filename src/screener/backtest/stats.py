from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd


def _round(value: float | int | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    num = float(value)
    if np.isnan(num) or np.isinf(num):
        return None
    return round(num, digits)


def _engine_label(engine: str) -> str:
    if engine == "bull":
        return "Bull"
    if engine == "weak":
        return "Weak"
    return engine


def _max_consecutive_losses(pnl_series: pd.Series) -> int:
    max_streak = 0
    streak = 0
    for pnl in pnl_series.tolist():
        if pnl < 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak


def _summary_for_subset(df: pd.DataFrame) -> Dict[str, float | int | None]:
    total_trades = int(len(df))
    if total_trades == 0:
        return {
            "total_trades": 0,
            "win_rate": None,
            "avg_win_pct": None,
            "avg_loss_pct": None,
            "max_win_pct": None,
            "max_loss_pct": None,
            "profit_factor": None,
            "expectancy_pct": None,
            "max_consecutive_losses": 0,
            "avg_hold_days": None,
        }

    pnl = df["pnl_pct"].astype(float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]

    win_rate = (len(wins) / total_trades) * 100.0
    avg_win = wins.mean() if len(wins) > 0 else None
    avg_loss = losses.mean() if len(losses) > 0 else None

    gross_profit = wins.sum() if len(wins) > 0 else 0.0
    gross_loss_abs = abs(losses.sum()) if len(losses) > 0 else 0.0
    profit_factor = (gross_profit / gross_loss_abs) if gross_loss_abs > 0 else None

    expectancy = pnl.mean()
    max_consec_losses = _max_consecutive_losses(pnl)
    avg_hold_days = float(df["hold_days"].astype(float).mean()) if "hold_days" in df.columns else None

    max_win = float(wins.max()) if len(wins) > 0 else None
    max_loss = float(losses.min()) if len(losses) > 0 else None

    return {
        "total_trades": total_trades,
        "win_rate": _round(win_rate, 2),
        "avg_win_pct": _round(avg_win, 4) if avg_win is not None else None,
        "avg_loss_pct": _round(avg_loss, 4) if avg_loss is not None else None,
        "max_win_pct": _round(max_win, 4) if max_win is not None else None,
        "max_loss_pct": _round(max_loss, 4) if max_loss is not None else None,
        "profit_factor": _round(profit_factor, 4) if profit_factor is not None else None,
        "expectancy_pct": _round(expectancy, 4),
        "max_consecutive_losses": int(max_consec_losses),
        "avg_hold_days": _round(avg_hold_days, 3) if avg_hold_days is not None else None,
    }


def summarize_trades(trades: pd.DataFrame) -> Dict[str, object]:
    if trades is None or trades.empty:
        return {
            "overall": _summary_for_subset(pd.DataFrame()),
            "by_engine": {
                "Bull": _summary_for_subset(pd.DataFrame()),
                "Weak": _summary_for_subset(pd.DataFrame()),
                "Combined": _summary_for_subset(pd.DataFrame()),
            },
            "by_year": {str(y): _summary_for_subset(pd.DataFrame()) for y in range(2020, 2025)},
            "by_year_engine": {
                str(y): {
                    "Bull": _summary_for_subset(pd.DataFrame()),
                    "Weak": _summary_for_subset(pd.DataFrame()),
                    "Combined": _summary_for_subset(pd.DataFrame()),
                }
                for y in range(2020, 2025)
            },
        }

    df = trades.copy()
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    df["year"] = df["entry_date"].dt.year.astype(int)

    overall = _summary_for_subset(df)

    by_engine: Dict[str, Dict[str, float | int | None]] = {
        "Bull": _summary_for_subset(df[df["engine"] == "bull"]),
        "Weak": _summary_for_subset(df[df["engine"] == "weak"]),
        "Combined": _summary_for_subset(df),
    }

    by_year: Dict[str, Dict[str, float | int | None]] = {}
    by_year_engine: Dict[str, Dict[str, Dict[str, float | int | None]]] = {}
    for year in range(2020, 2025):
        year_df = df[df["year"] == year]
        by_year[str(year)] = _summary_for_subset(year_df)
        by_year_engine[str(year)] = {
            "Bull": _summary_for_subset(year_df[year_df["engine"] == "bull"]),
            "Weak": _summary_for_subset(year_df[year_df["engine"] == "weak"]),
            "Combined": _summary_for_subset(year_df),
        }

    return {
        "overall": overall,
        "by_engine": by_engine,
        "by_year": by_year,
        "by_year_engine": by_year_engine,
    }
