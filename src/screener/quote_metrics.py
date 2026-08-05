from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from .config import Settings


MARKET_CAP_CACHE_MAX_AGE_DAYS = 3
BETA_1Y_CACHE_MAX_AGE_DAYS = 7
BETA_1Y_LOOKBACK_DAYS = 252
BETA_1Y_MIN_OBS = 60


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        num = float(value)
        if np.isnan(num) or np.isinf(num):
            return None
        return num
    except Exception:  # noqa: BLE001
        return None


def _safe_symbol(value: str) -> str:
    return str(value or "").strip().upper().replace("/", "_")


def _is_cache_fresh(path: Path, max_age_days: int) -> bool:
    if not path.exists():
        return False
    max_age = max(0, int(max_age_days))
    age = datetime.now(timezone.utc) - datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return age <= timedelta(days=max_age)


def _read_cached_payload(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:  # noqa: BLE001
        return {}
    return {}


def _write_cached_payload(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_payload = payload if isinstance(payload, dict) else {}
    path.write_text(json.dumps(safe_payload, ensure_ascii=False), encoding="utf-8")


def _quote_metrics_cache_dir(settings: Settings | None) -> Path:
    if settings is None:
        return Path("data/cache") / "quote_metrics"
    return settings.cache_path / "quote_metrics"


def _market_cap_cache_path(settings: Settings | None, yf_symbol: str) -> Path:
    return _quote_metrics_cache_dir(settings) / "market_cap" / f"{_safe_symbol(yf_symbol)}.json"


def _beta_cache_path(settings: Settings | None, yf_symbol: str, benchmark_symbol: str) -> Path:
    safe = _safe_symbol(yf_symbol)
    safe_bench = _safe_symbol(benchmark_symbol)
    return _quote_metrics_cache_dir(settings) / "beta_1y" / f"{safe}__vs__{safe_bench}.json"


def _adj_close_series(frame: pd.DataFrame | None) -> pd.Series:
    if frame is None or frame.empty:
        return pd.Series(dtype=float)
    if "Adj Close" in frame.columns:
        return pd.to_numeric(frame["Adj Close"], errors="coerce").dropna()
    if "Close" in frame.columns:
        return pd.to_numeric(frame["Close"], errors="coerce").dropna()
    return pd.Series(dtype=float)


def compute_beta_1y_from_prices(
    stock_prices: pd.DataFrame | None,
    benchmark_prices: pd.DataFrame | None,
    *,
    lookback_days: int = BETA_1Y_LOOKBACK_DAYS,
    min_obs: int = BETA_1Y_MIN_OBS,
) -> tuple[float | None, int]:
    stock_adj = _adj_close_series(stock_prices).tail(max(1, int(lookback_days)))
    bench_adj = _adj_close_series(benchmark_prices).tail(max(1, int(lookback_days)))

    if stock_adj.empty or bench_adj.empty:
        return None, 0

    stock_ret = stock_adj.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    bench_ret = bench_adj.pct_change().replace([np.inf, -np.inf], np.nan).dropna()

    aligned = pd.concat([stock_ret.rename("stock"), bench_ret.rename("bench")], axis=1, join="inner").dropna()
    obs = int(len(aligned))
    if obs < max(2, int(min_obs)):
        return None, obs

    bench_var = _safe_float(aligned["bench"].var(ddof=1))
    if bench_var is None or bench_var <= 0:
        return None, obs

    cov = _safe_float(aligned["stock"].cov(aligned["bench"]))
    if cov is None:
        return None, obs

    return _safe_float(cov / bench_var), obs


def _fetch_market_cap_fast(yf_symbol: str, logger: logging.Logger) -> tuple[float | None, str]:
    ticker = yf.Ticker(yf_symbol)

    # Primary source: fast_info.market_cap
    try:
        fast_info = ticker.fast_info
        value = None
        if hasattr(fast_info, "get"):
            value = _safe_float(fast_info.get("market_cap"))
        if value is None:
            value = _safe_float(getattr(fast_info, "market_cap", None))
        if value is not None:
            return value, "fast_info"
    except Exception as exc:  # noqa: BLE001
        logger.warning("fast_info market_cap fetch failed for %s: %s", yf_symbol, exc)

    return None, "unavailable"


def fetch_quote_metrics(
    yf_symbols: Iterable[str],
    prices_by_symbol: Dict[str, pd.DataFrame],
    logger: logging.Logger,
    settings: Settings | None = None,
    *,
    benchmark_symbol: str | None = None,
    legacy_info_by_symbol: Dict[str, Dict[str, Any]] | None = None,
) -> tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    symbols = sorted({str(s).strip().upper() for s in yf_symbols if str(s).strip()})
    metrics: Dict[str, Dict[str, Any]] = {}

    bench_symbol = str(benchmark_symbol or (settings.benchmark_symbol if settings else "SPY")).strip().upper()
    benchmark_prices = prices_by_symbol.get(bench_symbol)

    for yf_symbol in symbols:
        row = {
            "market_cap": None,
            "beta_1y": None,
            "market_cap_source": "unavailable",
            "beta_1y_source": "unavailable",
            "beta_1y_observations": 0,
        }

        market_cap_cache_path = _market_cap_cache_path(settings, yf_symbol)
        cached_market_cap = _read_cached_payload(market_cap_cache_path)

        if _is_cache_fresh(market_cap_cache_path, MARKET_CAP_CACHE_MAX_AGE_DAYS):
            mc = _safe_float(cached_market_cap.get("market_cap"))
            if mc is not None:
                row["market_cap"] = mc
                row["market_cap_source"] = "cache"

        if row["market_cap"] is None:
            market_cap, source = _fetch_market_cap_fast(yf_symbol, logger)
            if market_cap is not None:
                row["market_cap"] = market_cap
                row["market_cap_source"] = source
                _write_cached_payload(
                    market_cap_cache_path,
                    {
                        "yf_symbol": yf_symbol,
                        "market_cap": market_cap,
                        "source": source,
                        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
                    },
                )

        if row["market_cap"] is None:
            stale_mc = _safe_float(cached_market_cap.get("market_cap"))
            if stale_mc is not None:
                row["market_cap"] = stale_mc
                row["market_cap_source"] = "stale_cache"


        beta_cache_path = _beta_cache_path(settings, yf_symbol, bench_symbol)
        cached_beta = _read_cached_payload(beta_cache_path)

        if _is_cache_fresh(beta_cache_path, BETA_1Y_CACHE_MAX_AGE_DAYS):
            beta_cached = _safe_float(cached_beta.get("beta_1y"))
            if beta_cached is not None:
                row["beta_1y"] = beta_cached
                row["beta_1y_source"] = "cache"
                row["beta_1y_observations"] = int(_safe_float(cached_beta.get("observations")) or 0)

        if row["beta_1y"] is None:
            if yf_symbol == bench_symbol:
                row["beta_1y"] = 1.0
                row["beta_1y_source"] = "benchmark_self"
                row["beta_1y_observations"] = 0
            else:
                stock_prices = prices_by_symbol.get(yf_symbol)
                beta, obs = compute_beta_1y_from_prices(
                    stock_prices,
                    benchmark_prices,
                    lookback_days=BETA_1Y_LOOKBACK_DAYS,
                    min_obs=BETA_1Y_MIN_OBS,
                )
                if beta is not None:
                    row["beta_1y"] = beta
                    row["beta_1y_source"] = "computed_adj_close"
                    row["beta_1y_observations"] = int(obs)
                    _write_cached_payload(
                        beta_cache_path,
                        {
                            "yf_symbol": yf_symbol,
                            "benchmark_symbol": bench_symbol,
                            "beta_1y": beta,
                            "observations": int(obs),
                            "window_trading_days": int(BETA_1Y_LOOKBACK_DAYS),
                            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
                        },
                    )

        if row["beta_1y"] is None:
            stale_beta = _safe_float(cached_beta.get("beta_1y"))
            if stale_beta is not None:
                row["beta_1y"] = stale_beta
                row["beta_1y_source"] = "stale_cache"
                row["beta_1y_observations"] = int(_safe_float(cached_beta.get("observations")) or 0)


        metrics[yf_symbol] = row

    coverage = summarize_quote_metrics_coverage(symbols, metrics)

    market_cap_source_counts: Dict[str, int] = {}
    beta_source_counts: Dict[str, int] = {}
    for row in metrics.values():
        mc_source = str(row.get("market_cap_source") or "unavailable")
        beta_source = str(row.get("beta_1y_source") or "unavailable")
        market_cap_source_counts[mc_source] = market_cap_source_counts.get(mc_source, 0) + 1
        beta_source_counts[beta_source] = beta_source_counts.get(beta_source, 0) + 1

    diagnostics = {
        "coverage": coverage,
        "market_cap_source_counts": market_cap_source_counts,
        "beta_1y_source_counts": beta_source_counts,
        "beta_definition": {
            "name": "1Y beta",
            "method": "cov(stock_adj_close_daily_returns, benchmark_adj_close_daily_returns) / var(benchmark_adj_close_daily_returns)",
            "lookback_trading_days": int(BETA_1Y_LOOKBACK_DAYS),
            "min_observations": int(BETA_1Y_MIN_OBS),
            "benchmark_symbol": bench_symbol,
            "price_field": "Adj Close",
        },
    }

    return metrics, diagnostics


def summarize_quote_metrics_coverage(
    yf_symbols: Iterable[str],
    metrics_by_symbol: Dict[str, Dict[str, Any]] | None,
) -> Dict[str, Any]:
    symbols = sorted({str(s).strip().upper() for s in yf_symbols if str(s).strip()})
    metrics_map = metrics_by_symbol or {}

    success = []
    missing_market_cap = []
    missing_beta_1y = []
    missing_both = []

    for s in symbols:
        row = metrics_map.get(s) or {}
        market_cap = _safe_float(row.get("market_cap"))
        beta_1y = _safe_float(row.get("beta_1y"))

        if market_cap is not None and beta_1y is not None:
            success.append(s)
        elif market_cap is None and beta_1y is None:
            missing_both.append(s)
        elif market_cap is None:
            missing_market_cap.append(s)
        else:
            missing_beta_1y.append(s)

    attempted_count = len(symbols)
    success_count = len(success)

    return {
        "attempted_count": attempted_count,
        "success_count": success_count,
        "missing_market_cap_count": len(missing_market_cap),
        "missing_beta_1y_count": len(missing_beta_1y),
        "missing_both_count": len(missing_both),
        "success_rate": (success_count / attempted_count) if attempted_count else 0.0,
        "successful_symbols": success,
        "missing_market_cap_symbols": missing_market_cap,
        "missing_beta_1y_symbols": missing_beta_1y,
        "missing_both_symbols": missing_both,
    }
