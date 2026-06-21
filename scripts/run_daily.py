from __future__ import annotations

import json
import logging
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from screener.config import Settings
from screener.data import fetch_prices
from screener.engines import bull_candidates, select_playbook_candidates, weak_candidates
from screener.export import export_outputs
from screener.indicators import add_indicators, latest_metrics
from screener.quote_metrics import fetch_quote_metrics
from screener.market_condition import get_market_condition
from screener.ranking import rank_candidates
from screener.tracker import update_tracker_file
from screener.universe import UniverseItem, load_universe


def setup_logger() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    # yfinance can emit non-fatal "possibly delisted; no price data found" errors
    # during quote metadata probes (e.g., fast_info/history internals).
    # Keep screener logs clean while preserving runtime behavior.
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    return logging.getLogger("screener")


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        v = float(value)
        if np.isnan(v) or np.isinf(v):
            return None
        return v
    except Exception:  # noqa: BLE001
        return None


def _build_rows(
    items: List[UniverseItem],
    enriched: Dict[str, object],
    quote_metrics_by_symbol: Dict[str, Dict[str, Any]],
    logger: logging.Logger,
) -> List[Dict]:
    rows: List[Dict] = []
    for item in items:
        df = enriched.get(item.yf_symbol)
        if df is None:
            continue
        try:
            metrics = latest_metrics(df)
            row = {
                "symbol": item.symbol,
                "yf_symbol": item.yf_symbol,
                **metrics,
                "market_cap": _num((quote_metrics_by_symbol.get(item.yf_symbol) or {}).get("market_cap")),
                "beta_1y": _num((quote_metrics_by_symbol.get(item.yf_symbol) or {}).get("beta_1y")),
            }
            rows.append(row)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping %s while building metrics: %s", item.symbol, exc)
    return rows


def _build_chart_series(df, window: int = 252) -> Dict[str, Any]:
    tail = df.tail(window).copy()

    def _col_values(frame, name: str, fallback: str | None = None) -> List[float | None]:
        if name in frame.columns:
            return [_num(v) for v in frame[name].tolist()]
        if fallback and fallback in frame.columns:
            return [_num(v) for v in frame[fallback].tolist()]
        return []

    if tail.empty:
        return {
            "dates": [],
            "close": [],
            "adj_close": [],
            "volume": [],
            "ema9": [],
            "ema21": [],
            "sma20": [],
            "sma50": [],
            "sma200": [],
            "bb_lower": [],
        }

    return {
        "dates": [idx.strftime("%Y-%m-%d") for idx in tail.index],
        "close": _col_values(tail, "Close"),
        "adj_close": _col_values(tail, "signal_close", fallback="Close"),
        "volume": _col_values(tail, "Volume"),
        "ema9": _col_values(tail, "ema9"),
        "ema21": _col_values(tail, "ema21"),
        "sma20": _col_values(tail, "sma20"),
        "sma50": _col_values(tail, "sma50"),
        "sma200": _col_values(tail, "sma200"),
        "bb_lower": _col_values(tail, "bb_lower"),
    }


def _regime_risk_fraction(regime_label: str, settings: Settings) -> float:
    regime = str(regime_label or "Bull").strip().capitalize()
    if regime == "Bear":
        return float(settings.risk_per_trade_bear)
    if regime == "Choppy":
        return float(settings.risk_per_trade_choppy)
    return float(settings.risk_per_trade_bull)


def _compute_stop_loss(row: Dict[str, Any], signal_close: float | None, atr14: float | None) -> tuple[float | None, str]:
    if signal_close is None or signal_close <= 0:
        return None, "no_signal_close"

    playbook_id = str(row.get("playbook_id") or "").strip().upper()

    atr_stop = None
    if atr14 is not None and atr14 > 0:
        if playbook_id == "BREAKOUT":
            atr_stop = signal_close - (1.8 * atr14)
        elif playbook_id == "PULLBACK_ENTRY":
            atr_stop = signal_close - (1.6 * atr14)
        elif playbook_id == "TIGHT_BASE":
            atr_stop = signal_close - (2.0 * atr14)
        elif playbook_id == "CAPITULATION_RECLAIM":
            atr_stop = signal_close - (1.2 * atr14)
        else:
            atr_stop = signal_close - (2.0 * atr14)

    structure_stop = None
    if playbook_id == "BREAKOUT":
        pivot_price = _num(row.get("pivot_price"))
        if pivot_price is not None and pivot_price > 0:
            structure_stop = pivot_price * 0.995
    elif playbook_id == "PULLBACK_ENTRY":
        entry_triangle_price = _num(row.get("entry_triangle_price"))
        sma20 = _num(row.get("sma20"))
        values = [x for x in [entry_triangle_price, sma20] if x is not None and x > 0]
        if values:
            structure_stop = min(values)
    elif playbook_id == "TIGHT_BASE":
        pivot_price = _num(row.get("pivot_price"))
        if pivot_price is not None and pivot_price > 0:
            structure_stop = pivot_price * 0.96
    elif playbook_id == "CAPITULATION_RECLAIM":
        bb_lower = _num(row.get("bb_lower"))
        if bb_lower is not None and bb_lower > 0:
            structure_stop = bb_lower

    choices = [x for x in [atr_stop, structure_stop] if x is not None and x > 0]
    if not choices:
        return None, "no_stop_available"

    return min(choices), "playbook_structure_plus_atr"


def _enrich_candidates(
    candidates: List[Dict],
    fundamentals_by_symbol: Dict[str, Dict],
    *,
    settings: Settings,
    regime_label: str,
    trade_policy: Dict[str, Any],
) -> List[Dict]:
    out: List[Dict] = []

    trade_allowed = bool(trade_policy.get("trade_allowed", True))
    equity = float(settings.initial_capital)
    max_exposure_value = equity * float(settings.max_position_exposure_pct)
    risk_fraction = _regime_risk_fraction(regime_label, settings)

    for c in candidates:
        row = dict(c)

        atr14 = _num(row.get("atr14"))
        signal_close = _num(row.get("adj_close"))
        if signal_close is None:
            signal_close = _num(row.get("close"))

        entry_reference = signal_close
        stop_loss, stop_method = _compute_stop_loss(row, signal_close, atr14)

        activation_level = None
        trailing_stop_offset = None
        if atr14 is not None and signal_close is not None and atr14 > 0 and signal_close > 0:
            activation_level = entry_reference + (2.0 * atr14)
            trailing_stop_offset = 1.5 * atr14

        risk_per_trade_value = equity * risk_fraction
        per_share_risk = None
        shares_by_risk = 0
        shares_by_exposure = 0
        max_shares = 0

        if signal_close is not None and signal_close > 0:
            shares_by_exposure = int(max(0, math.floor(max_exposure_value / signal_close)))

        if stop_loss is not None and signal_close is not None and signal_close > stop_loss:
            per_share_risk = signal_close - stop_loss
            shares_by_risk = int(max(0, math.floor(risk_per_trade_value / per_share_risk)))

        if shares_by_risk > 0 and shares_by_exposure > 0:
            max_shares = min(shares_by_risk, shares_by_exposure)
        else:
            max_shares = shares_by_exposure

        intent = str(row.get("intent") or "watchlist").strip().lower()
        if (not trade_allowed) or intent != "trade":
            max_shares = 0

        row["risk"] = {
            "signal_close": signal_close,
            "entry_reference": entry_reference,
            "atr14": atr14,
            "stop_loss": stop_loss,
            "activation_level": activation_level,
            "take_profit": activation_level,
            "trailing_stop_offset": trailing_stop_offset,
            "max_hold_days": 15,
            "method": stop_method,
            "position_sizing": {
                "equity": equity,
                "regime": str(regime_label or "Bull").capitalize(),
                "risk_per_trade_fraction": risk_fraction,
                "risk_per_trade_value": risk_per_trade_value,
                "max_position_exposure_pct": float(settings.max_position_exposure_pct),
                "max_position_value": max_exposure_value,
                "per_share_risk": per_share_risk,
                "shares_by_risk": shares_by_risk,
                "shares_by_exposure": shares_by_exposure,
                "max_shares": max_shares,
                "trade_allowed": trade_allowed,
            },
        }

        yf_symbol = str(row.get("yf_symbol") or "")
        row["fundamentals"] = fundamentals_by_symbol.get(
            yf_symbol,
            {
                "roe": None,
                "pe": None,
                "revenue_growth_qoq": None,
                "revenue_growth_yoy": None,
            },
        )

        out.append(row)

    return out


def export_daily_data(
    symbols: List[str],
    prices_by_symbol: Dict[str, object] | None = None,
    logger: logging.Logger | None = None,
) -> None:
    out_dir = ROOT / "docs" / "data" / "daily"
    out_dir.mkdir(parents=True, exist_ok=True)

    unique_symbols = sorted({str(s) for s in symbols if str(s).strip()})
    for symbol in unique_symbols:
        df = (prices_by_symbol or {}).get(symbol)
        frame = df.copy() if hasattr(df, "copy") else None

        if frame is None or frame.empty:
            payload = {
                "Date": [],
                "Open": [],
                "High": [],
                "Low": [],
                "Close": [],
                "Volume": [],
            }
        else:
            frame = frame.sort_index().tail(252 * 3)
            payload = {
                "Date": [idx.strftime("%Y-%m-%d") for idx in frame.index],
                "Open": [_num(v) for v in frame["Open"].tolist()] if "Open" in frame.columns else [],
                "High": [_num(v) for v in frame["High"].tolist()] if "High" in frame.columns else [],
                "Low": [_num(v) for v in frame["Low"].tolist()] if "Low" in frame.columns else [],
                "Close": [_num(v) for v in frame["Close"].tolist()] if "Close" in frame.columns else [],
                "Volume": [_num(v) for v in frame["Volume"].tolist()] if "Volume" in frame.columns else [],
            }
            if "Adj Close" in frame.columns:
                payload["Adj Close"] = [_num(v) for v in frame["Adj Close"].tolist()]

        safe_symbol = symbol.replace("/", "_")
        out_path = out_dir / f"{safe_symbol}.json"
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if logger:
        logger.info("Exported 3Y daily data JSON for %s symbols to %s", len(unique_symbols), out_dir)


def main() -> int:
    settings = Settings()
    logger = setup_logger()
    run_started_at_utc = datetime.now(timezone.utc)
    run_started_perf = time.perf_counter()

    universe = load_universe(settings.universe_file)
    yf_symbols = sorted({u.yf_symbol for u in universe})
    if settings.benchmark_symbol not in yf_symbols:
        yf_symbols.append(settings.benchmark_symbol)

    prices, data_diag = fetch_prices(yf_symbols=yf_symbols, settings=settings, logger=logger)
    export_daily_data(yf_symbols, prices_by_symbol=prices, logger=logger)
    quote_metrics_by_symbol, quote_metrics_diag = fetch_quote_metrics(
        yf_symbols,
        prices,
        logger,
        settings=settings,
        benchmark_symbol=settings.benchmark_symbol,
    )
    quote_metrics_coverage = quote_metrics_diag.get("coverage") or {}
    logger.info(
        "Quote metrics coverage: success=%s missing_market_cap=%s missing_beta_1y=%s missing_both=%s attempted=%s success_rate=%.2f%%",
        quote_metrics_coverage.get("success_count", 0),
        quote_metrics_coverage.get("missing_market_cap_count", 0),
        quote_metrics_coverage.get("missing_beta_1y_count", 0),
        quote_metrics_coverage.get("missing_both_count", 0),
        quote_metrics_coverage.get("attempted_count", 0),
        float(quote_metrics_coverage.get("success_rate", 0.0)) * 100.0,
    )

    benchmark_df = prices.get(settings.benchmark_symbol)
    if benchmark_df is None or benchmark_df.empty:
        logger.error("Benchmark %s data unavailable, aborting", settings.benchmark_symbol)
        return 1

    enriched: Dict[str, object] = {}
    skipped = list(data_diag.skipped)

    benchmark_enriched = add_indicators(
        benchmark_df,
        breakout_lookback=settings.breakout_lookback,
        rsi_length=settings.rsi_length,
        bb_length=settings.bb_length,
        bb_std=settings.bb_std,
        sma_regime_length=settings.sma_regime_length,
    )
    if benchmark_enriched.empty or benchmark_enriched["sma200"].dropna().empty:
        logger.error("Benchmark %s lacks enough history for SMA200", settings.benchmark_symbol)
        return 1

    enriched[settings.benchmark_symbol] = benchmark_enriched

    for item in universe:
        raw = prices.get(item.yf_symbol)
        if raw is None or raw.empty:
            skipped.append({"symbol": item.symbol, "yf_symbol": item.yf_symbol, "reason": "missing_price_data"})
            continue

        try:
            e = add_indicators(
                raw,
                breakout_lookback=settings.breakout_lookback,
                rsi_length=settings.rsi_length,
                bb_length=settings.bb_length,
                bb_std=settings.bb_std,
                sma_regime_length=settings.sma_regime_length,
            )
            if e.empty or len(e) < max(settings.sma_regime_length, settings.bb_length, settings.breakout_lookback):
                skipped.append({"symbol": item.symbol, "yf_symbol": item.yf_symbol, "reason": "insufficient_history"})
                continue
            enriched[item.yf_symbol] = e
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping %s due to indicator error: %s", item.symbol, exc)
            skipped.append(
                {
                    "symbol": item.symbol,
                    "yf_symbol": item.yf_symbol,
                    "reason": f"indicator_error:{exc.__class__.__name__}",
                }
            )

    print("Generating market condition data...")
    market_condition = get_market_condition()
    regime_label = str(market_condition.get("regime_label") or "Bull").strip().capitalize()

    rows = _build_rows(universe, enriched, quote_metrics_by_symbol, logger)

    bull_raw_candidates = bull_candidates(
        rows,
        min_price=settings.min_price,
        min_market_cap=settings.min_market_cap,
        min_beta_1y=settings.min_beta_1y,
        min_volume=settings.min_volume,
        min_avg_dollar_volume_20d=settings.min_avg_dollar_volume_20d,
        regime_label=regime_label,
    )
    weak_raw_candidates = weak_candidates(
        rows,
        min_price=settings.min_price,
        min_market_cap=settings.min_market_cap,
        min_beta_1y=settings.min_beta_1y,
        min_volume=settings.min_volume,
        weak_rsi_threshold=settings.weak_rsi_threshold,
        min_avg_dollar_volume_20d=settings.min_avg_dollar_volume_20d,
    )

    raw_candidates = bull_raw_candidates + weak_raw_candidates

    playbook_candidates, trade_policy = select_playbook_candidates(
        raw_candidates,
        regime_label=regime_label,
        min_price=settings.min_price,
        min_avg_dollar_volume_20d=settings.min_avg_dollar_volume_20d,
        max_atr_pct=settings.max_atr_pct,
        min_avg_dollar_volume_20d_bull=settings.min_avg_dollar_volume_20d_bull,
        min_avg_dollar_volume_20d_choppy=settings.min_avg_dollar_volume_20d_choppy,
        min_avg_dollar_volume_20d_bear=settings.min_avg_dollar_volume_20d_bear,
        min_atr_dollars=settings.min_atr_dollars,
        atr_pct_tier_lt_20=settings.atr_pct_tier_lt_20,
        atr_pct_tier_20_to_100=settings.atr_pct_tier_20_to_100,
        atr_pct_tier_gt_100=settings.atr_pct_tier_gt_100,
    )

    engine_name = "playbook"

    ranked = rank_candidates(playbook_candidates, settings.max_candidates)

    top20_yf_symbols = sorted({str(c.get("yf_symbol")) for c in ranked[:20] if c.get("yf_symbol")})
    fundamentals_by_symbol: Dict[str, Dict] = {s: {} for s in top20_yf_symbols}
    ranked = _enrich_candidates(
        ranked,
        fundamentals_by_symbol,
        settings=settings,
        regime_label=regime_label,
        trade_policy=trade_policy,
    )

    charts_by_symbol = {}
    for c in ranked[:20]:
        yf_symbol = str(c.get("yf_symbol") or "")
        df = enriched.get(yf_symbol)
        if df is None:
            continue
        charts_by_symbol[yf_symbol] = _build_chart_series(df, window=252)

    run_finished_at_utc = datetime.now(timezone.utc)
    run_duration_seconds = max(0.0, time.perf_counter() - run_started_perf)
    run_timing = {
        "started_at_utc": run_started_at_utc.isoformat(),
        "finished_at_utc": run_finished_at_utc.isoformat(),
        "duration_seconds": round(run_duration_seconds, 3),
    }

    diagnostics = {
        "counts": {
            "downloaded_symbols": data_diag.downloaded_symbols,
            "cached_symbols": data_diag.cached_symbols,
            "missing_or_skipped_count": len(skipped),
            "rows_with_metrics": len(rows),
            "raw_candidates_count": len(raw_candidates),
            "raw_bull_candidates_count": len(bull_raw_candidates),
            "raw_weak_candidates_count": len(weak_raw_candidates),
            "playbook_candidates_count": len(playbook_candidates),
            "ranked_candidates_count": len(ranked),
            "qualified_trade_count": int(trade_policy.get("qualified_trade_count", 0)),
            "watchlist_count": int(trade_policy.get("watchlist_count", 0)),
            "quote_metrics_attempted_count": int(quote_metrics_coverage.get("attempted_count", 0)),
            "quote_metrics_success_count": int(quote_metrics_coverage.get("success_count", 0)),
            "quote_metrics_missing_market_cap_count": int(quote_metrics_coverage.get("missing_market_cap_count", 0)),
            "quote_metrics_missing_beta_1y_count": int(quote_metrics_coverage.get("missing_beta_1y_count", 0)),
            "quote_metrics_missing_both_count": int(quote_metrics_coverage.get("missing_both_count", 0)),
            "quote_metrics_success_rate": float(quote_metrics_coverage.get("success_rate", 0.0)),
            "run_duration_seconds": float(run_timing["duration_seconds"]),
        },
        "run_timing": run_timing,
        "quote_metrics": quote_metrics_diag,
        "quote_metrics_coverage": quote_metrics_coverage,
        "playbook_policy": trade_policy,
        "skipped_tickers": skipped,
        "warnings": [],
        "errors": [],
        # Backward-compatible keys for legacy frontend
        "downloaded_symbols": data_diag.downloaded_symbols,
        "cached_symbols": data_diag.cached_symbols,
        "missing_or_skipped_count": len(skipped),
        "skipped": skipped,
        "rows_with_metrics": len(rows),
    }

    latest_benchmark_close = _num(benchmark_enriched["Close"].iloc[-1]) if "Close" in benchmark_enriched.columns else None
    latest_benchmark_sma200 = _num(benchmark_enriched["sma200"].iloc[-1]) if "sma200" in benchmark_enriched.columns else None
    benchmark_snapshot = {
        "symbol": settings.benchmark_symbol,
        "close": latest_benchmark_close,
        "sma200": latest_benchmark_sma200,
        "above_sma200": bool(
            latest_benchmark_close is not None
            and latest_benchmark_sma200 is not None
            and latest_benchmark_close > latest_benchmark_sma200
        ),
    }

    chart_data = {
        "window_trading_days": 252,
        "default_visibility": {
            "close": True,
            "sma20": True,
            "sma50": True,
            "sma200": True,
            "ema9": False,
            "ema21": False,
            "bb_lower": False,
            "volume": False,
        },
        "benchmark": {
            "symbol": settings.benchmark_symbol,
            "series": _build_chart_series(benchmark_enriched, window=252),
        },
        "symbols": charts_by_symbol,
    }

    export_outputs(
        settings_snapshot=settings.snapshot(),
        benchmark=benchmark_snapshot,
        candidates=ranked,
        diagnostics=diagnostics,
        regime=regime_label,
        engine=engine_name,
        universe_size=len(universe),
        json_path=settings.output_json,
        csv_path=settings.output_csv,
        chart_data=chart_data,
        trade_policy=trade_policy,
        risk_policy={
            "initial_capital": float(settings.initial_capital),
            "max_positions": int(settings.max_positions),
            "max_position_exposure_pct": float(settings.max_position_exposure_pct),
            "risk_per_trade": {
                "bull": float(settings.risk_per_trade_bull),
                "choppy": float(settings.risk_per_trade_choppy),
                "bear": float(settings.risk_per_trade_bear),
            },
            "monthly_drawdown_circuit_breaker": {
                "soft": float(settings.monthly_drawdown_soft),
                "hard": float(settings.monthly_drawdown_hard),
            },
        },
    )

    tracker_payload = update_tracker_file(
        ranked_candidates=ranked,
        rows_with_metrics=rows,
        enriched_by_yf_symbol=enriched,
    )

    market_condition_path = Path("docs/data/market_condition.json")
    market_condition_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Saving market condition data to {market_condition_path}...")
    market_condition_path.write_text(json.dumps(market_condition, indent=2), encoding="utf-8")

    logger.info(
        "Finished run: regime=%s engine=%s candidates=%s universe=%s tracker_active=%s tracker_dropped=%s runtime=%.3fs",
        regime_label,
        engine_name,
        len(ranked),
        len(universe),
        len(tracker_payload.get("active", [])),
        len(tracker_payload.get("dropped", [])),
        run_timing["duration_seconds"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
