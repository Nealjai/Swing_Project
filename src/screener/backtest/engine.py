from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Iterable, List, Literal

import numpy as np
import pandas as pd

from screener.config import Settings
from screener.data import fetch_prices
from screener.fundamentals import fetch_ticker_info
from screener.indicators import add_indicators

EngineSelection = Literal["bull", "weak", "both"]


@dataclass(frozen=True)
class BacktestConfig:
    start_date: str = "2020-01-01"
    end_date: str = "2024-12-31"
    engine: EngineSelection = "both"
    warmup_bars: int = 200


@dataclass(frozen=True)
class BacktestResult:
    trades: pd.DataFrame
    candidates: pd.DataFrame
    diagnostics: Dict[str, object]
    prices: Dict[str, pd.DataFrame]


def _to_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        num = float(value)
        if np.isnan(num) or np.isinf(num):
            return None
        return num
    except Exception:  # noqa: BLE001
        return None


def _engine_enabled(selection: EngineSelection, candidate_engine: str) -> bool:
    if selection == "both":
        return candidate_engine in {"bull", "weak"}
    return selection == candidate_engine


def _regime_state_series(benchmark_df: pd.DataFrame) -> pd.Series:
    valid = benchmark_df[["Close", "sma200"]].dropna()
    if valid.empty:
        return pd.Series(dtype=object)
    state = np.where(valid["Close"] > valid["sma200"], "bull", "weak")
    return pd.Series(state, index=valid.index)


def _simulate_symbol(
    symbol: str,
    yf_symbol: str,
    enriched: pd.DataFrame,
    regime_by_date: pd.Series,
    config: BacktestConfig,
    settings: Settings,
    market_cap: float | None,
    beta_1y: float | None,
) -> List[Dict[str, object]]:
    if enriched.empty:
        return []

    start_ts = pd.Timestamp(config.start_date)
    end_ts = pd.Timestamp(config.end_date)

    frame = enriched.sort_index().copy()
    frame = frame.loc[frame.index <= end_ts]
    if frame.empty:
        return []

    idx = frame.index
    open_px = frame["Open"].to_numpy(dtype=float)
    raw_close_px = frame["Close"].to_numpy(dtype=float)
    signal_close_px = frame["signal_close"].to_numpy(dtype=float)
    volume = frame["Volume"].to_numpy(dtype=float)
    high_20d = frame["high_20d"].to_numpy(dtype=float)
    rsi14 = frame["rsi14"].to_numpy(dtype=float)
    avg_dv = frame["avg_dollar_volume_20d"].to_numpy(dtype=float)
    bb_lower = frame["bb_lower"].to_numpy(dtype=float)
    atr14 = frame["atr14"].to_numpy(dtype=float)

    if market_cap is None or beta_1y is None:
        return []

    common_ok = (
        np.isfinite(signal_close_px)
        & np.isfinite(volume)
        & (signal_close_px > float(settings.min_price))
        & (volume >= float(settings.min_volume))
        & np.isfinite(avg_dv)
        & (avg_dv >= float(settings.min_avg_dollar_volume_20d))
        & (market_cap > float(settings.min_market_cap))
        & (beta_1y > float(settings.min_beta_1y))
    )

    bull_signal = (
        common_ok
        & np.isfinite(high_20d)
        & np.isfinite(rsi14)
        & (signal_close_px >= (high_20d * 0.995))
    )

    weak_signal = (
        common_ok
        & np.isfinite(bb_lower)
        & np.isfinite(rsi14)
        & (signal_close_px <= bb_lower)
        & (rsi14 <= float(settings.weak_rsi_threshold))
    )

    trades: List[Dict[str, object]] = []

    i = max(config.warmup_bars, 0)
    n = len(frame)
    while i < n - 1:
        signal_date = idx[i]
        if signal_date < start_ts or signal_date > end_ts:
            i += 1
            continue

        regime_state = regime_by_date.get(signal_date)
        if regime_state not in {"bull", "weak"}:
            i += 1
            continue

        signal_engine: str | None = None
        if regime_state == "bull" and bull_signal[i] and _engine_enabled(config.engine, "bull"):
            signal_engine = "bull"
        elif regime_state == "weak" and weak_signal[i] and _engine_enabled(config.engine, "weak"):
            signal_engine = "weak"

        if signal_engine is None:
            i += 1
            continue

        entry_i = i + 1
        if entry_i >= n:
            break

        entry_date = idx[entry_i]
        if entry_date > end_ts:
            i += 1
            continue

        entry_price = float(open_px[entry_i])
        if not np.isfinite(entry_price) or entry_price <= 0:
            i += 1
            continue

        atr_val = float(atr14[i]) if np.isfinite(atr14[i]) else np.nan
        bb_lower_val = float(bb_lower[i]) if np.isfinite(bb_lower[i]) else np.nan
        signal_close = float(signal_close_px[i]) if np.isfinite(signal_close_px[i]) else np.nan

        if not np.isfinite(atr_val) or not np.isfinite(bb_lower_val) or not np.isfinite(signal_close):
            i += 1
            continue

        tp_level = signal_close + (3.0 * atr_val)
        sl_level = bb_lower_val - atr_val

        last_idx_in_range = int(np.searchsorted(idx.values, end_ts.to_datetime64(), side="right") - 1)
        if last_idx_in_range < entry_i:
            i += 1
            continue

        exit_i: int | None = None
        exit_reason: str | None = None
        for j in range(entry_i, last_idx_in_range + 1):
            px = float(raw_close_px[j])
            if not np.isfinite(px):
                continue
            if px >= tp_level:
                exit_i = j
                exit_reason = "TP"
                break
            if px <= sl_level:
                exit_i = j
                exit_reason = "SL"
                break

        if exit_i is None:
            exit_i = last_idx_in_range
            exit_reason = "EOT"

        exit_price = float(raw_close_px[exit_i])
        if not np.isfinite(exit_price):
            i = exit_i + 1
            continue

        hold_days = max(1, int(exit_i - entry_i + 1))
        pnl_pct = ((exit_price / entry_price) - 1.0) * 100.0

        trades.append(
            {
                "symbol": symbol,
                "engine": signal_engine,
                "signal_date": signal_date.strftime("%Y-%m-%d"),
                "entry_date": entry_date.strftime("%Y-%m-%d"),
                "entry_price": entry_price,
                "exit_date": idx[exit_i].strftime("%Y-%m-%d"),
                "exit_price": exit_price,
                "exit_reason": exit_reason,
                "hold_days": hold_days,
                "pnl_pct": pnl_pct,
                "regime_state": regime_state,
                "yf_symbol": yf_symbol,
                "signal_close": signal_close,
                "signal_raw_close": float(raw_close_px[i]) if np.isfinite(raw_close_px[i]) else None,
                "signal_atr14": atr_val,
                "signal_bb_lower": bb_lower_val,
                "tp_level": float(tp_level),
                "sl_level": float(sl_level),
                "signal_rsi14": float(rsi14[i]) if np.isfinite(rsi14[i]) else None,
                "signal_high_20d": float(high_20d[i]) if np.isfinite(high_20d[i]) else None,
                "signal_avg_dollar_volume_20d": float(avg_dv[i]) if np.isfinite(avg_dv[i]) else None,
                "signal_volume": float(volume[i]) if np.isfinite(volume[i]) else None,
                "market_cap": market_cap,
                "beta_1y": beta_1y,
            }
        )

        i = exit_i + 1

    return trades


def _generate_symbol_candidates(
    symbol: str,
    yf_symbol: str,
    enriched: pd.DataFrame,
    regime_by_date: pd.Series,
    config: BacktestConfig,
    settings: Settings,
    market_cap: float | None,
    beta_1y: float | None,
) -> List[Dict[str, object]]:
    """Generate candidate trades per signal date without skip-forward.

    This is used by the portfolio simulator where entries may be rejected due to
    portfolio constraints; candidate generation must therefore keep all eligible
    signal opportunities.
    """
    if enriched.empty:
        return []

    start_ts = pd.Timestamp(config.start_date)
    end_ts = pd.Timestamp(config.end_date)

    frame = enriched.sort_index().copy()
    frame = frame.loc[frame.index <= end_ts]
    if frame.empty:
        return []

    idx = frame.index
    open_px = frame["Open"].to_numpy(dtype=float)
    raw_close_px = frame["Close"].to_numpy(dtype=float)
    signal_close_px = frame["signal_close"].to_numpy(dtype=float)
    volume = frame["Volume"].to_numpy(dtype=float)
    high_20d = frame["high_20d"].to_numpy(dtype=float)
    rsi14 = frame["rsi14"].to_numpy(dtype=float)
    avg_dv = frame["avg_dollar_volume_20d"].to_numpy(dtype=float)
    bb_lower = frame["bb_lower"].to_numpy(dtype=float)
    atr14 = frame["atr14"].to_numpy(dtype=float)

    if market_cap is None or beta_1y is None:
        return []

    common_ok = (
        np.isfinite(signal_close_px)
        & np.isfinite(volume)
        & (signal_close_px > float(settings.min_price))
        & (volume >= float(settings.min_volume))
        & np.isfinite(avg_dv)
        & (avg_dv >= float(settings.min_avg_dollar_volume_20d))
        & (market_cap > float(settings.min_market_cap))
        & (beta_1y > float(settings.min_beta_1y))
    )

    bull_signal = (
        common_ok
        & np.isfinite(high_20d)
        & np.isfinite(rsi14)
        & (signal_close_px >= (high_20d * 0.995))
    )

    weak_signal = (
        common_ok
        & np.isfinite(bb_lower)
        & np.isfinite(rsi14)
        & (signal_close_px <= bb_lower)
        & (rsi14 <= float(settings.weak_rsi_threshold))
    )

    candidates: List[Dict[str, object]] = []
    n = len(frame)
    first_i = max(config.warmup_bars, 0)

    for i in range(first_i, n - 1):
        signal_date = idx[i]
        if signal_date < start_ts or signal_date > end_ts:
            continue

        regime_state = regime_by_date.get(signal_date)
        if regime_state not in {"bull", "weak"}:
            continue

        signal_engine: str | None = None
        if regime_state == "bull" and bull_signal[i] and _engine_enabled(config.engine, "bull"):
            signal_engine = "bull"
        elif regime_state == "weak" and weak_signal[i] and _engine_enabled(config.engine, "weak"):
            signal_engine = "weak"

        if signal_engine is None:
            continue

        entry_i = i + 1
        if entry_i >= n:
            continue

        entry_date = idx[entry_i]
        if entry_date > end_ts:
            continue

        entry_price = float(open_px[entry_i])
        if not np.isfinite(entry_price) or entry_price <= 0:
            continue

        atr_val = float(atr14[i]) if np.isfinite(atr14[i]) else np.nan
        bb_lower_val = float(bb_lower[i]) if np.isfinite(bb_lower[i]) else np.nan
        signal_close = float(signal_close_px[i]) if np.isfinite(signal_close_px[i]) else np.nan

        if not np.isfinite(atr_val) or not np.isfinite(bb_lower_val) or not np.isfinite(signal_close):
            continue

        tp_level = signal_close + (3.0 * atr_val)
        sl_level = bb_lower_val - atr_val

        last_idx_in_range = int(np.searchsorted(idx.values, end_ts.to_datetime64(), side="right") - 1)
        if last_idx_in_range < entry_i:
            continue

        exit_i: int | None = None
        exit_reason: str | None = None
        for j in range(entry_i, last_idx_in_range + 1):
            px = float(raw_close_px[j])
            if not np.isfinite(px):
                continue
            if px >= tp_level:
                exit_i = j
                exit_reason = "TP"
                break
            if px <= sl_level:
                exit_i = j
                exit_reason = "SL"
                break

        if exit_i is None:
            exit_i = last_idx_in_range
            exit_reason = "EOT"

        exit_price = float(raw_close_px[exit_i])
        if not np.isfinite(exit_price):
            continue

        hold_days = max(1, int(exit_i - entry_i + 1))
        pnl_pct = ((exit_price / entry_price) - 1.0) * 100.0

        candidates.append(
            {
                "symbol": symbol,
                "engine": signal_engine,
                "signal_date": signal_date.strftime("%Y-%m-%d"),
                "entry_date": entry_date.strftime("%Y-%m-%d"),
                "entry_price": entry_price,
                "exit_date": idx[exit_i].strftime("%Y-%m-%d"),
                "exit_price": exit_price,
                "exit_reason": exit_reason,
                "hold_days": hold_days,
                "pnl_pct": pnl_pct,
                "regime_state": regime_state,
                "yf_symbol": yf_symbol,
                "signal_close": signal_close,
                "signal_raw_close": float(raw_close_px[i]) if np.isfinite(raw_close_px[i]) else None,
                "signal_atr14": atr_val,
                "signal_bb_lower": bb_lower_val,
                "tp_level": float(tp_level),
                "sl_level": float(sl_level),
                "signal_rsi14": float(rsi14[i]) if np.isfinite(rsi14[i]) else None,
                "signal_high_20d": float(high_20d[i]) if np.isfinite(high_20d[i]) else None,
                "signal_avg_dollar_volume_20d": float(avg_dv[i]) if np.isfinite(avg_dv[i]) else None,
                "signal_volume": float(volume[i]) if np.isfinite(volume[i]) else None,
                "market_cap": market_cap,
                "beta_1y": beta_1y,
            }
        )

    return candidates


def run_backtest(
    symbols: Iterable[str],
    settings: Settings,
    config: BacktestConfig,
    logger: logging.Logger,
    *,
    force_refresh: bool = False,
    market_aware_refresh: bool = True,
) -> BacktestResult:
    unique_symbols = sorted({str(s).strip().upper() for s in symbols if str(s).strip()})
    if settings.benchmark_symbol not in unique_symbols:
        unique_symbols.append(settings.benchmark_symbol)

    prices, data_diag = fetch_prices(
        yf_symbols=unique_symbols,
        settings=settings,
        logger=logger,
        force_refresh=force_refresh,
        market_aware_refresh=market_aware_refresh,
    )
    info_by_symbol = fetch_ticker_info(unique_symbols, logger)

    benchmark_df = prices.get(settings.benchmark_symbol)
    if benchmark_df is None or benchmark_df.empty:
        raise RuntimeError(f"Benchmark {settings.benchmark_symbol} data unavailable")

    benchmark_enriched = add_indicators(
        benchmark_df,
        breakout_lookback=settings.breakout_lookback,
        rsi_length=settings.rsi_length,
        bb_length=settings.bb_length,
        bb_std=settings.bb_std,
        sma_regime_length=settings.sma_regime_length,
    )
    if benchmark_enriched.empty or benchmark_enriched["sma200"].dropna().empty:
        raise RuntimeError(f"Benchmark {settings.benchmark_symbol} lacks sufficient data for SMA200")

    regime_by_date = _regime_state_series(benchmark_enriched)

    all_trades: List[Dict[str, object]] = []
    all_candidates: List[Dict[str, object]] = []
    skipped: List[Dict[str, str]] = list(data_diag.skipped)

    for yf_symbol in unique_symbols:
        if yf_symbol == settings.benchmark_symbol:
            continue

        raw = prices.get(yf_symbol)
        if raw is None or raw.empty:
            skipped.append({"yf_symbol": yf_symbol, "reason": "missing_price_data"})
            continue

        enriched = add_indicators(
            raw,
            breakout_lookback=settings.breakout_lookback,
            rsi_length=settings.rsi_length,
            bb_length=settings.bb_length,
            bb_std=settings.bb_std,
            sma_regime_length=settings.sma_regime_length,
        )

        if enriched.empty or len(enriched) <= config.warmup_bars:
            skipped.append({"yf_symbol": yf_symbol, "reason": "insufficient_history"})
            continue

        info = info_by_symbol.get(yf_symbol) or {}
        market_cap = _to_float(info.get("marketCap"))
        beta_1y = _to_float(info.get("beta"))
        if market_cap is None or beta_1y is None:
            skipped.append({"yf_symbol": yf_symbol, "reason": "missing_market_cap_or_beta"})
            continue

        symbol_candidates = _generate_symbol_candidates(
            symbol=yf_symbol,
            yf_symbol=yf_symbol,
            enriched=enriched,
            regime_by_date=regime_by_date,
            config=config,
            settings=settings,
            market_cap=market_cap,
            beta_1y=beta_1y,
        )
        all_candidates.extend(symbol_candidates)

        # Legacy per-symbol trade simulation with skip-forward semantics.
        all_trades.extend(
            _simulate_symbol(
                symbol=yf_symbol,
                yf_symbol=yf_symbol,
                enriched=enriched,
                regime_by_date=regime_by_date,
                config=config,
                settings=settings,
                market_cap=market_cap,
                beta_1y=beta_1y,
            )
        )

    trades_df = pd.DataFrame(all_trades)
    if not trades_df.empty:
        trades_df = trades_df.sort_values(["entry_date", "symbol", "engine"]).reset_index(drop=True)

    candidates_df = pd.DataFrame(all_candidates)
    if not candidates_df.empty:
        candidates_df = candidates_df.sort_values(["entry_date", "symbol", "engine", "signal_date"]).reset_index(drop=True)

    diagnostics = {
        "counts": {
            "symbols_requested": len(unique_symbols),
            "symbols_excluding_benchmark": max(0, len(unique_symbols) - 1),
            "downloaded_symbols": data_diag.downloaded_symbols,
            "cached_symbols": data_diag.cached_symbols,
            "skipped_symbols": len(skipped),
            "trades": int(len(trades_df)),
            "candidates": int(len(candidates_df)),
        },
        "skipped_symbols": skipped,
        "config": {
            "start_date": config.start_date,
            "end_date": config.end_date,
            "engine": config.engine,
            "warmup_bars": config.warmup_bars,
            "min_avg_dollar_volume_20d": float(settings.min_avg_dollar_volume_20d),
            "force_refresh": bool(force_refresh),
            "market_aware_refresh": bool(market_aware_refresh),
        },
    }

    return BacktestResult(trades=trades_df, candidates=candidates_df, diagnostics=diagnostics, prices=prices)
