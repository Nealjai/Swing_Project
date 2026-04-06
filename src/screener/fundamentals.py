from __future__ import annotations

import logging
from typing import Dict, Iterable

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


def fetch_ticker_info(yf_symbols: Iterable[str], logger: logging.Logger) -> Dict[str, Dict]:
    out: Dict[str, Dict] = {}

    for yf_symbol in yf_symbols:
        info: Dict = {}
        try:
            ticker = yf.Ticker(yf_symbol)
            info = ticker.info or {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ticker info fetch failed for %s: %s", yf_symbol, exc)

        out[yf_symbol] = info

    return out


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
            info = (info_by_symbol or {}).get(yf_symbol) or {}

            fundamentals["roe"] = _safe_float(info.get("returnOnEquity"))
            fundamentals["pe"] = _safe_float(info.get("trailingPE"))

            qoq, yoy = _extract_quarterly_revenue_growth(ticker)
            fundamentals["revenue_growth_qoq"] = qoq
            fundamentals["revenue_growth_yoy"] = yoy

            if fundamentals["revenue_growth_yoy"] is None:
                fundamentals["revenue_growth_yoy"] = _safe_float(info.get("revenueGrowth"))

        except Exception as exc:  # noqa: BLE001
            logger.warning("Fundamentals fetch failed for %s: %s", yf_symbol, exc)

        out[yf_symbol] = fundamentals

    return out
