from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import yfinance as yf

from .config import Settings

REQUIRED_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]
OPTIONAL_COLUMNS = ["Adj Close"]


@dataclass
class DataDiagnostics:
    downloaded_symbols: int
    cached_symbols: int
    skipped: List[dict]


def _cache_file(cache_dir: Path, yf_symbol: str) -> Path:
    safe = yf_symbol.replace("/", "_")
    return cache_dir / f"{safe}.csv"


def _is_fresh(path: Path, max_age_days: int, required_start: str | None = None) -> bool:
    if not path.exists():
        return False

    age = datetime.now(timezone.utc) - datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    if age > timedelta(days=max_age_days):
        return False

    if required_start:
        try:
            required_start_ts = pd.Timestamp(required_start)
            cached = pd.read_csv(path, usecols=["Date"])
            if cached.empty:
                return False
            cached_dates = pd.to_datetime(cached["Date"], errors="coerce").dropna()
            if cached_dates.empty:
                return False
            # Cache is only acceptable if it fully covers the requested window.
            if cached_dates.min() > required_start_ts:
                return False
        except Exception:  # noqa: BLE001
            return False

    return True


def _read_cached(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["Date"])
    if df.empty:
        return pd.DataFrame()
    df = df.set_index("Date")
    return df


def _write_cache(path: Path, df: pd.DataFrame) -> None:
    out = df.copy()
    out.index.name = "Date"
    out.to_csv(path)


def _clean_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    if isinstance(df.columns, pd.MultiIndex):
        return pd.DataFrame()

    cols = [c for c in REQUIRED_COLUMNS if c in df.columns]
    if len(cols) < len(REQUIRED_COLUMNS):
        return pd.DataFrame()

    selected_cols = REQUIRED_COLUMNS + [c for c in OPTIONAL_COLUMNS if c in df.columns]
    out = df[selected_cols].copy()
    if "Adj Close" not in out.columns:
        out["Adj Close"] = out["Close"]

    out = out.dropna(subset=["Close"])
    out = out.sort_index()
    return out


def _extract_symbol_frame(download_df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if download_df.empty:
        return pd.DataFrame()

    if isinstance(download_df.columns, pd.MultiIndex):
        if symbol not in download_df.columns.get_level_values(0):
            return pd.DataFrame()
        candidate = download_df[symbol]
        if isinstance(candidate, pd.Series):
            candidate = candidate.to_frame()
        return _clean_ohlcv(candidate)

    return _clean_ohlcv(download_df)


def fetch_prices(
    yf_symbols: List[str],
    settings: Settings,
    logger: logging.Logger,
) -> Tuple[Dict[str, pd.DataFrame], DataDiagnostics]:
    settings.cache_path.mkdir(parents=True, exist_ok=True)

    prices: Dict[str, pd.DataFrame] = {}
    stale_symbols: List[str] = []
    skipped: List[dict] = []
    cached_symbols = 0

    start = (datetime.now(timezone.utc) - timedelta(days=settings.lookback_calendar_days)).date().isoformat()

    for symbol in yf_symbols:
        cache_path = _cache_file(settings.cache_path, symbol)
        if _is_fresh(cache_path, settings.cache_max_age_days, required_start=start):
            cached = _read_cached(cache_path)
            if not cached.empty:
                prices[symbol] = cached
                cached_symbols += 1
                continue
        stale_symbols.append(symbol)

    downloaded_symbols = 0
    for i in range(0, len(stale_symbols), settings.download_batch_size):
        chunk = stale_symbols[i : i + settings.download_batch_size]
        if not chunk:
            continue
        try:
            df = yf.download(
                tickers=chunk,
                start=start,
                interval="1d",
                auto_adjust=False,
                progress=False,
                group_by="ticker",
                threads=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed yfinance batch download for %s", chunk)
            for symbol in chunk:
                skipped.append({"yf_symbol": symbol, "reason": f"download_error:{exc.__class__.__name__}"})
            continue

        for symbol in chunk:
            frame = _extract_symbol_frame(df, symbol)
            if frame.empty:
                skipped.append({"yf_symbol": symbol, "reason": "empty_or_missing_ohlcv"})
                logger.warning("Skipping %s: empty/missing OHLCV", symbol)
                continue
            prices[symbol] = frame
            downloaded_symbols += 1
            _write_cache(_cache_file(settings.cache_path, symbol), frame)

    diagnostics = DataDiagnostics(
        downloaded_symbols=downloaded_symbols,
        cached_symbols=cached_symbols,
        skipped=skipped,
    )
    return prices, diagnostics
