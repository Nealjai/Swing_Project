from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterable

import numpy as np
import yfinance as yf

def _safe_float(value) -> float | None:
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


def _extract_quarterly_revenue_growth(ticker: yf.Ticker) -> tuple[float | None, float | None]:
    """
    Returns (qoq, yoy) revenue growth as ratios (e.g., 0.12 = +12%).
    """
    try:
        qf = ticker.quarterly_financials
    except Exception:  # noqa: BLE001
        return None, None

    if qf is None or qf.empty:
        return None, None

    rev_row_name = None
    for candidate in ["Total Revenue", "Revenue", "Operating Revenue"]:
        if candidate in qf.index:
            rev_row_name = candidate
            break

    if rev_row_name is None:
        return None, None

    rev = qf.loc[rev_row_name].dropna()
    if rev.empty:
        return None, None

    rev = rev.sort_index()

    qoq = None
    yoy = None

    if len(rev) >= 2 and float(rev.iloc[-2]) != 0:
        qoq = (float(rev.iloc[-1]) / float(rev.iloc[-2])) - 1.0

    if len(rev) >= 5 and float(rev.iloc[-5]) != 0:
        yoy = (float(rev.iloc[-1]) / float(rev.iloc[-5])) - 1.0

    return _safe_float(qoq), _safe_float(yoy)


def fetch_ticker_info(
    yf_symbols: Iterable[str],
    logger: logging.Logger,
    settings: object | None = None,
) -> Dict[str, Dict]:
    symbols = sorted({str(s).strip().upper() for s in yf_symbols if str(s).strip()})
    if symbols:
        logger.info("Ticker info fetching is disabled in no-info mode; returning empty payloads for %s symbols", len(symbols))
    return {s: {} for s in symbols}


def summarize_ticker_info_coverage(
    yf_symbols: Iterable[str],
    info_by_symbol: Dict[str, Dict] | None,
) -> Dict[str, Any]:
    symbols = sorted({str(s).strip().upper() for s in yf_symbols if str(s).strip()})
    info_map = info_by_symbol or {}

    success_symbols = [s for s in symbols if isinstance(info_map.get(s), dict) and bool(info_map.get(s))]
    empty_symbols = [s for s in symbols if s in info_map and not bool(info_map.get(s))]
    missing_symbols = [s for s in symbols if s not in info_map]

    attempted_count = len(symbols)
    success_count = len(success_symbols)
    empty_count = len(empty_symbols)
    missing_count = len(missing_symbols)
    success_rate = (success_count / attempted_count) if attempted_count else 0.0

    return {
        "attempted_count": attempted_count,
        "success_count": success_count,
        "empty_count": empty_count,
        "missing_count": missing_count,
        "success_rate": success_rate,
        "successful_symbols": success_symbols,
        "empty_symbols": empty_symbols,
        "missing_symbols": missing_symbols,
    }


def fetch_fundamentals(
    yf_symbols: Iterable[str],
    logger: logging.Logger,
    info_by_symbol: Dict[str, Dict] | None = None,
) -> Dict[str, Dict]:
    out: Dict[str, Dict] = {}

    for yf_symbol in yf_symbols:
        fundamentals = {
            "roe": None,
            "pe": None,
            "revenue_growth_qoq": None,
            "revenue_growth_yoy": None,
        }

        try:
            ticker = yf.Ticker(yf_symbol)
            qoq, yoy = _extract_quarterly_revenue_growth(ticker)
            fundamentals["revenue_growth_qoq"] = qoq
            fundamentals["revenue_growth_yoy"] = yoy
        except Exception as exc:  # noqa: BLE001
            logger.warning("Fundamentals fetch failed for %s: %s", yf_symbol, exc)

        out[yf_symbol] = fundamentals

    return out
