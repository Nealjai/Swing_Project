from __future__ import annotations

from dataclasses import dataclass
from math import floor, sqrt
from typing import Dict, List

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PortfolioConfig:
    initial_capital: float = 10_000.0
    max_positions: int = 5
    slippage_pct_each_side: float = 0.0005
    commission_per_side: float = 0.32
    monthly_drawdown_limit_pct: float = 6.0
    monthly_risk_per_trade_pct: float = 1.0
    risk_free_rate_annual: float = 0.0
    trading_days_per_year: int = 252
    share_rounding: str = "floor"
    entry_priority: str = "avg_dollar_volume_20d_desc"


@dataclass(frozen=True)
class PortfolioResult:
    executed_trades: pd.DataFrame
    fills_log: pd.DataFrame
    equity_curve: pd.DataFrame
    monthly_returns: pd.DataFrame
    metrics: Dict[str, float | int | None]


def _safe_float(v: object) -> float | None:
    try:
        if v is None:
            return None
        f = float(v)
        if not np.isfinite(f):
            return None
        return f
    except Exception:  # noqa: BLE001
        return None


def _prepare_calendar(
    prices_by_symbol: Dict[str, pd.DataFrame],
    benchmark_symbol: str,
    start_date: str,
    end_date: str,
    candidates: pd.DataFrame,
) -> pd.DatetimeIndex:
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)

    benchmark_df = prices_by_symbol.get(benchmark_symbol)
    if benchmark_df is not None and not benchmark_df.empty:
        cal = pd.DatetimeIndex(benchmark_df.index).sort_values()
        cal = cal[(cal >= start_ts) & (cal <= end_ts)]
        if len(cal) > 0:
            return cal

    if candidates.empty:
        return pd.DatetimeIndex([])

    entry_dates = pd.to_datetime(candidates["entry_date"], errors="coerce")
    exit_dates = pd.to_datetime(candidates["exit_date"], errors="coerce")
    dates = pd.DatetimeIndex(pd.concat([entry_dates, exit_dates], axis=0).dropna().unique()).sort_values()
    return dates[(dates >= start_ts) & (dates <= end_ts)]


def _build_price_map(
    prices_by_symbol: Dict[str, pd.DataFrame],
    symbols: List[str],
    calendar: pd.DatetimeIndex,
    column: str,
) -> Dict[str, pd.Series]:
    out: Dict[str, pd.Series] = {}
    for symbol in symbols:
        df = prices_by_symbol.get(symbol)
        if df is None or df.empty or column not in df.columns:
            out[symbol] = pd.Series(index=calendar, dtype=float)
            continue
        series = pd.to_numeric(df[column], errors="coerce")
        series = series.reindex(calendar)
        if column in {"Close", "Adj Close"}:
            series = series.ffill()
        out[symbol] = series
    return out


def _annualized_cagr(equity_curve: pd.DataFrame, initial_capital: float) -> float | None:
    if equity_curve.empty:
        return None
    first_date = pd.Timestamp(equity_curve["date"].iloc[0])
    last_date = pd.Timestamp(equity_curve["date"].iloc[-1])
    days = (last_date - first_date).days
    if days <= 0:
        return None
    final_equity = float(equity_curve["equity"].iloc[-1])
    if initial_capital <= 0 or final_equity <= 0:
        return None
    years = days / 365.25
    if years <= 0:
        return None
    return ((final_equity / initial_capital) ** (1.0 / years) - 1.0) * 100.0


def _compute_sharpe_sortino(
    equity_curve: pd.DataFrame,
    risk_free_rate_annual: float,
    trading_days_per_year: int,
) -> tuple[float | None, float | None]:
    if equity_curve.empty or len(equity_curve) < 2:
        return None, None

    returns = pd.to_numeric(equity_curve["equity"], errors="coerce").pct_change().dropna()
    if returns.empty:
        return None, None

    daily_rf = risk_free_rate_annual / float(trading_days_per_year)
    excess = returns - daily_rf

    sharpe: float | None = None
    std_excess = float(excess.std(ddof=1)) if len(excess) > 1 else 0.0
    if np.isfinite(std_excess) and std_excess > 0:
        sharpe = float(excess.mean()) / std_excess * sqrt(float(trading_days_per_year))

    downside = np.minimum(excess.to_numpy(dtype=float), 0.0)
    downside_dev = float(np.sqrt(np.mean(np.square(downside)))) if len(downside) else 0.0
    sortino: float | None = None
    if np.isfinite(downside_dev) and downside_dev > 0:
        sortino = float(excess.mean()) / downside_dev * sqrt(float(trading_days_per_year))

    return sharpe, sortino


def _build_monthly_returns(equity_curve: pd.DataFrame, initial_capital: float) -> pd.DataFrame:
    if equity_curve.empty:
        return pd.DataFrame(columns=["month", "return_pct"]) 

    curve = equity_curve.copy()
    curve["date"] = pd.to_datetime(curve["date"])
    curve["month"] = curve["date"].dt.to_period("M").astype(str)
    month_end_equity = curve.groupby("month", as_index=False)["equity"].last()

    prev_equity = float(initial_capital)
    rows: List[Dict[str, object]] = []
    for _, r in month_end_equity.iterrows():
        month = str(r["month"])
        eq = float(r["equity"])
        if prev_equity <= 0:
            ret = None
        else:
            ret = ((eq / prev_equity) - 1.0) * 100.0
        rows.append({"month": month, "return_pct": ret})
        prev_equity = eq
    return pd.DataFrame(rows)


def simulate_portfolio(
    *,
    candidates: pd.DataFrame,
    prices_by_symbol: Dict[str, pd.DataFrame],
    benchmark_symbol: str,
    start_date: str,
    end_date: str,
    config: PortfolioConfig,
) -> PortfolioResult:
    if candidates is None or candidates.empty:
        empty_curve = pd.DataFrame(columns=["date", "equity", "cash", "positions_value", "drawdown_pct", "halted_new_entries"]) 
        empty_monthly = pd.DataFrame(columns=["month", "return_pct"])
        return PortfolioResult(
            executed_trades=pd.DataFrame(),
            fills_log=pd.DataFrame(),
            equity_curve=empty_curve,
            monthly_returns=empty_monthly,
            metrics={
                "total_return_pct": 0.0,
                "cagr_pct": None,
                "max_drawdown_pct": 0.0,
                "exposure_pct": 0.0,
                "months_halted": 0,
                "sharpe": None,
                "sortino": None,
                "avg_positions": 0.0,
                "turnover_pct": 0.0,
                "executed_trades": 0,
                "rejected_entries": 0,
            },
        )

    cands = candidates.copy()
    cands["entry_date"] = pd.to_datetime(cands["entry_date"], errors="coerce")
    cands["exit_date"] = pd.to_datetime(cands["exit_date"], errors="coerce")
    cands["entry_price"] = pd.to_numeric(cands["entry_price"], errors="coerce")
    cands["exit_price"] = pd.to_numeric(cands["exit_price"], errors="coerce")
    cands["sl_level"] = pd.to_numeric(cands.get("sl_level"), errors="coerce")
    cands["signal_avg_dollar_volume_20d"] = pd.to_numeric(cands.get("signal_avg_dollar_volume_20d"), errors="coerce")

    cands = cands.dropna(subset=["entry_date", "exit_date", "entry_price", "exit_price"])
    cands = cands[cands["entry_date"] <= cands["exit_date"]].copy()

    calendar = _prepare_calendar(
        prices_by_symbol=prices_by_symbol,
        benchmark_symbol=benchmark_symbol,
        start_date=start_date,
        end_date=end_date,
        candidates=cands,
    )
    if len(calendar) == 0:
        empty_curve = pd.DataFrame(columns=["date", "equity", "cash", "positions_value", "drawdown_pct", "halted_new_entries"]) 
        empty_monthly = pd.DataFrame(columns=["month", "return_pct"])
        return PortfolioResult(
            executed_trades=pd.DataFrame(),
            fills_log=pd.DataFrame(),
            equity_curve=empty_curve,
            monthly_returns=empty_monthly,
            metrics={
                "total_return_pct": 0.0,
                "cagr_pct": None,
                "max_drawdown_pct": 0.0,
                "exposure_pct": 0.0,
                "months_halted": 0,
                "sharpe": None,
                "sortino": None,
                "avg_positions": 0.0,
                "turnover_pct": 0.0,
                "executed_trades": 0,
                "rejected_entries": 0,
            },
        )

    cands = cands[cands["entry_date"].isin(calendar) & cands["exit_date"].isin(calendar)].copy()
    cands = cands.sort_values(["entry_date", "signal_avg_dollar_volume_20d", "symbol"], ascending=[True, False, True]).reset_index(drop=True)

    symbols = sorted({str(s) for s in cands["yf_symbol"].dropna().astype(str).unique().tolist()})
    open_map = _build_price_map(prices_by_symbol=prices_by_symbol, symbols=symbols, calendar=calendar, column="Open")
    high_map = _build_price_map(prices_by_symbol=prices_by_symbol, symbols=symbols, calendar=calendar, column="High")
    low_map = _build_price_map(prices_by_symbol=prices_by_symbol, symbols=symbols, calendar=calendar, column="Low")
    close_map = _build_price_map(prices_by_symbol=prices_by_symbol, symbols=symbols, calendar=calendar, column="Close")

    by_entry_date: Dict[pd.Timestamp, pd.DataFrame] = {
        d: g.copy() for d, g in cands.groupby("entry_date", sort=True)
    }

    cash = float(config.initial_capital)
    open_positions: Dict[str, Dict[str, object]] = {}
    fills_log: List[Dict[str, object]] = []
    executed_trades: List[Dict[str, object]] = []
    equity_rows: List[Dict[str, object]] = []

    turnover_dollars = 0.0
    exposure_days = 0
    sum_positions_count = 0.0

    month_key: str | None = None
    month_start_equity = float(config.initial_capital)
    month_halted = False
    halted_months: set[str] = set()

    peak_equity = float(config.initial_capital)
    prev_equity = float(config.initial_capital)

    for day in calendar:
        day_month = day.strftime("%Y-%m")
        if day_month != month_key:
            month_key = day_month
            month_start_equity = float(prev_equity)
            month_halted = False

        if not month_halted:
            day_candidates = by_entry_date.get(day)
            if day_candidates is not None and not day_candidates.empty:
                available_slots = max(0, int(config.max_positions) - len(open_positions))

                if available_slots <= 0:
                    for _, c in day_candidates.iterrows():
                        fills_log.append(
                            {
                                "date": day.strftime("%Y-%m-%d"),
                                "symbol": c.get("symbol"),
                                "yf_symbol": c.get("yf_symbol"),
                                "engine": c.get("engine"),
                                "entry_date": day.strftime("%Y-%m-%d"),
                                "status": "rejected",
                                "reason": "max_positions_reached",
                            }
                        )
                else:
                    for _, c in day_candidates.iterrows():
                        sym = str(c.get("yf_symbol") or "").strip()
                        if not sym:
                            continue
                        if sym in open_positions:
                            fills_log.append(
                                {
                                    "date": day.strftime("%Y-%m-%d"),
                                    "symbol": c.get("symbol"),
                                    "yf_symbol": sym,
                                    "engine": c.get("engine"),
                                    "entry_date": day.strftime("%Y-%m-%d"),
                                    "status": "rejected",
                                    "reason": "symbol_already_open",
                                }
                            )
                            continue

                        if available_slots <= 0:
                            fills_log.append(
                                {
                                    "date": day.strftime("%Y-%m-%d"),
                                    "symbol": c.get("symbol"),
                                    "yf_symbol": sym,
                                    "engine": c.get("engine"),
                                    "entry_date": day.strftime("%Y-%m-%d"),
                                    "status": "rejected",
                                    "reason": "max_positions_reached",
                                }
                            )
                            continue

                        raw_entry = _safe_float(c.get("entry_price"))
                        raw_exit = _safe_float(c.get("exit_price"))
                        sl_level = _safe_float(c.get("sl_level"))
                        if raw_entry is None or raw_entry <= 0 or raw_exit is None or raw_exit <= 0:
                            fills_log.append(
                                {
                                    "date": day.strftime("%Y-%m-%d"),
                                    "symbol": c.get("symbol"),
                                    "yf_symbol": sym,
                                    "engine": c.get("engine"),
                                    "entry_date": day.strftime("%Y-%m-%d"),
                                    "status": "rejected",
                                    "reason": "invalid_price",
                                }
                            )
                            continue

                        entry_fill = raw_entry * (1.0 + float(config.slippage_pct_each_side))
                        equal_weight_notional = max(0.0, float(prev_equity) / float(config.max_positions))

                        shares_equal = floor(equal_weight_notional / entry_fill)
                        shares_cash = floor(max(0.0, cash - float(config.commission_per_side)) / entry_fill)

                        risk_cap_dollars = month_start_equity * (float(config.monthly_risk_per_trade_pct) / 100.0)
                        risk_per_share = (entry_fill - sl_level) if sl_level is not None else None
                        if risk_per_share is None or not np.isfinite(risk_per_share) or risk_per_share <= 0:
                            fills_log.append(
                                {
                                    "date": day.strftime("%Y-%m-%d"),
                                    "symbol": c.get("symbol"),
                                    "yf_symbol": sym,
                                    "engine": c.get("engine"),
                                    "entry_date": day.strftime("%Y-%m-%d"),
                                    "status": "rejected",
                                    "reason": "invalid_risk_distance",
                                }
                            )
                            continue
                        shares_risk = floor(risk_cap_dollars / risk_per_share)

                        shares = int(max(0, min(shares_equal, shares_cash, shares_risk)))
                        if shares <= 0:
                            fills_log.append(
                                {
                                    "date": day.strftime("%Y-%m-%d"),
                                    "symbol": c.get("symbol"),
                                    "yf_symbol": sym,
                                    "engine": c.get("engine"),
                                    "entry_date": day.strftime("%Y-%m-%d"),
                                    "status": "rejected",
                                    "reason": "sizing_zero",
                                }
                            )
                            continue

                        entry_cost = (shares * entry_fill) + float(config.commission_per_side)
                        if entry_cost > cash + 1e-12:
                            fills_log.append(
                                {
                                    "date": day.strftime("%Y-%m-%d"),
                                    "symbol": c.get("symbol"),
                                    "yf_symbol": sym,
                                    "engine": c.get("engine"),
                                    "entry_date": day.strftime("%Y-%m-%d"),
                                    "status": "rejected",
                                    "reason": "insufficient_cash",
                                }
                            )
                            continue

                        cash -= entry_cost
                        turnover_dollars += shares * entry_fill
                        available_slots -= 1

                        open_positions[sym] = {
                            "symbol": c.get("symbol"),
                            "yf_symbol": sym,
                            "engine": c.get("engine"),
                            "entry_date": day,
                            "entry_fill": entry_fill,
                            "entry_raw": raw_entry,
                            "entry_cost": entry_cost,
                            "shares": shares,
                            "planned_exit_date": pd.Timestamp(c.get("exit_date")),
                            "planned_exit_raw": raw_exit,
                            "exit_reason": c.get("exit_reason"),
                            "sl_level": sl_level,
                            "tp_level": _safe_float(c.get("tp_level")),
                            "signal_avg_dollar_volume_20d": _safe_float(c.get("signal_avg_dollar_volume_20d")),
                        }

                        fills_log.append(
                            {
                                "date": day.strftime("%Y-%m-%d"),
                                "symbol": c.get("symbol"),
                                "yf_symbol": sym,
                                "engine": c.get("engine"),
                                "entry_date": day.strftime("%Y-%m-%d"),
                                "status": "accepted",
                                "reason": "entered",
                                "shares": shares,
                                "entry_fill": entry_fill,
                            }
                        )
        else:
            day_candidates = by_entry_date.get(day)
            if day_candidates is not None and not day_candidates.empty:
                for _, c in day_candidates.iterrows():
                    fills_log.append(
                        {
                            "date": day.strftime("%Y-%m-%d"),
                            "symbol": c.get("symbol"),
                            "yf_symbol": c.get("yf_symbol"),
                            "engine": c.get("engine"),
                            "entry_date": day.strftime("%Y-%m-%d"),
                            "status": "rejected",
                            "reason": "monthly_drawdown_halt",
                        }
                    )

        # Exit logic: intraday TP/SL using daily High/Low, with gap-aware open handling.
        to_close: List[tuple[str, Dict[str, object], float, str]] = []
        for sym, pos in open_positions.items():
            open_series = open_map.get(sym)
            high_series = high_map.get(sym)
            low_series = low_map.get(sym)
            close_series = close_map.get(sym)

            open_px = None if open_series is None else _safe_float(open_series.loc[day])
            high_px = None if high_series is None else _safe_float(high_series.loc[day])
            low_px = None if low_series is None else _safe_float(low_series.loc[day])
            close_px = None if close_series is None else _safe_float(close_series.loc[day])

            sl_level = _safe_float(pos.get("sl_level"))
            tp_level = _safe_float(pos.get("tp_level"))
            planned_exit_date = pd.Timestamp(pos.get("planned_exit_date"))
            planned_exit_raw = _safe_float(pos.get("planned_exit_raw"))

            exit_raw: float | None = None
            exit_reason = ""

            if sl_level is not None and open_px is not None and open_px <= sl_level:
                exit_raw = open_px
                exit_reason = "sl_gap_open"
            elif tp_level is not None and open_px is not None and open_px >= tp_level:
                exit_raw = open_px
                exit_reason = "tp_gap_open"
            else:
                hit_sl = sl_level is not None and low_px is not None and low_px <= sl_level
                hit_tp = tp_level is not None and high_px is not None and high_px >= tp_level

                if hit_sl and hit_tp:
                    exit_raw = float(sl_level)
                    exit_reason = "sl_tp_same_day_stop_priority"
                elif hit_sl:
                    exit_raw = float(sl_level)
                    exit_reason = "sl_intraday"
                elif hit_tp:
                    exit_raw = float(tp_level)
                    exit_reason = "tp_intraday"
                elif day >= planned_exit_date:
                    if close_px is not None:
                        exit_raw = float(close_px)
                        exit_reason = "planned_exit_date_close"
                    elif planned_exit_raw is not None and planned_exit_raw > 0:
                        exit_raw = float(planned_exit_raw)
                        exit_reason = "planned_exit_raw_fallback"

            if exit_raw is not None and exit_raw > 0:
                to_close.append((sym, pos, float(exit_raw), exit_reason))

        for sym, pos, exit_raw, exit_reason in to_close:
            exit_fill = exit_raw * (1.0 - float(config.slippage_pct_each_side))
            proceeds = (float(pos["shares"]) * exit_fill) - float(config.commission_per_side)
            cash += proceeds
            turnover_dollars += float(pos["shares"]) * exit_fill

            pnl_dollar = proceeds - float(pos["entry_cost"])
            basis = float(pos["entry_cost"])
            pnl_pct = ((pnl_dollar / basis) * 100.0) if basis > 0 else None

            executed_trades.append(
                {
                    "symbol": pos["symbol"],
                    "yf_symbol": sym,
                    "engine": pos["engine"],
                    "entry_date": pd.Timestamp(pos["entry_date"]).strftime("%Y-%m-%d"),
                    "exit_date": day.strftime("%Y-%m-%d"),
                    "shares": int(pos["shares"]),
                    "entry_price_raw": float(pos["entry_raw"]),
                    "entry_price_fill": float(pos["entry_fill"]),
                    "exit_price_raw": float(exit_raw),
                    "exit_price_fill": float(exit_fill),
                    "entry_cost": float(pos["entry_cost"]),
                    "exit_proceeds": float(proceeds),
                    "pnl_dollar": float(pnl_dollar),
                    "pnl_pct": pnl_pct,
                    "exit_reason": exit_reason or pos.get("exit_reason"),
                    "sl_level": pos.get("sl_level"),
                    "tp_level": pos.get("tp_level"),
                    "signal_avg_dollar_volume_20d": pos.get("signal_avg_dollar_volume_20d"),
                }
            )
            del open_positions[sym]

        # End-of-day mark-to-market.
        positions_value = 0.0
        for sym, pos in open_positions.items():
            close_series = close_map.get(sym)
            close_px = None if close_series is None else _safe_float(close_series.loc[day])
            if close_px is None:
                close_px = float(pos["entry_fill"])
            positions_value += float(pos["shares"]) * float(close_px)

        equity = cash + positions_value
        peak_equity = max(peak_equity, equity)
        drawdown_pct = ((equity / peak_equity) - 1.0) * 100.0 if peak_equity > 0 else 0.0

        threshold = month_start_equity * (1.0 - (float(config.monthly_drawdown_limit_pct) / 100.0))
        if equity < threshold and not month_halted:
            month_halted = True
            halted_months.add(day_month)

        positions_count = len(open_positions)
        sum_positions_count += float(positions_count)
        if positions_count > 0:
            exposure_days += 1

        equity_rows.append(
            {
                "date": day.strftime("%Y-%m-%d"),
                "equity": float(equity),
                "cash": float(cash),
                "positions_value": float(positions_value),
                "positions_count": int(positions_count),
                "drawdown_pct": float(drawdown_pct),
                "halted_new_entries": bool(month_halted),
            }
        )
        prev_equity = float(equity)

    equity_curve = pd.DataFrame(equity_rows)
    fills_df = pd.DataFrame(fills_log)
    executed_df = pd.DataFrame(executed_trades)

    monthly_returns = _build_monthly_returns(equity_curve=equity_curve, initial_capital=float(config.initial_capital))

    final_equity = float(equity_curve["equity"].iloc[-1]) if not equity_curve.empty else float(config.initial_capital)
    total_return_pct = ((final_equity / float(config.initial_capital)) - 1.0) * 100.0 if config.initial_capital > 0 else 0.0
    cagr_pct = _annualized_cagr(equity_curve=equity_curve, initial_capital=float(config.initial_capital))
    max_drawdown_pct = abs(float(equity_curve["drawdown_pct"].min())) if not equity_curve.empty else 0.0
    exposure_pct = (float(exposure_days) / float(len(equity_curve)) * 100.0) if len(equity_curve) else 0.0
    avg_positions = (sum_positions_count / float(len(equity_curve))) if len(equity_curve) else 0.0
    turnover_pct = (turnover_dollars / float(config.initial_capital) * 100.0) if config.initial_capital > 0 else 0.0
    sharpe, sortino = _compute_sharpe_sortino(
        equity_curve=equity_curve,
        risk_free_rate_annual=float(config.risk_free_rate_annual),
        trading_days_per_year=int(config.trading_days_per_year),
    )

    metrics: Dict[str, float | int | None] = {
        "total_return_pct": round(total_return_pct, 4),
        "cagr_pct": round(cagr_pct, 4) if cagr_pct is not None else None,
        "max_drawdown_pct": round(max_drawdown_pct, 4),
        "exposure_pct": round(exposure_pct, 4),
        "months_halted": int(len(halted_months)),
        "sharpe": round(float(sharpe), 4) if sharpe is not None and np.isfinite(sharpe) else None,
        "sortino": round(float(sortino), 4) if sortino is not None and np.isfinite(sortino) else None,
        "avg_positions": round(float(avg_positions), 4),
        "turnover_pct": round(float(turnover_pct), 4),
        "executed_trades": int(len(executed_df)),
        "rejected_entries": int(len(fills_df[fills_df.get("status") == "rejected"])) if not fills_df.empty else 0,
    }

    return PortfolioResult(
        executed_trades=executed_df,
        fills_log=fills_df,
        equity_curve=equity_curve,
        monthly_returns=monthly_returns,
        metrics=metrics,
    )
