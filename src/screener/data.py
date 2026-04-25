from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple
from zoneinfo import ZoneInfo

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


def _manifest_file(cache_dir: Path) -> Path:
    return cache_dir / "market_data_manifest.json"


def _previous_trading_day(current: date) -> date:
    d = current - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _current_market_session_date(now_utc: datetime | None = None) -> date:
    now = now_utc or datetime.now(timezone.utc)
    now_ny = now.astimezone(ZoneInfo("America/New_York"))

    if now_ny.weekday() >= 5:
        return _previous_trading_day(now_ny.date())

    market_close_ny = dt_time(hour=16, minute=0)
    if now_ny.time() >= market_close_ny:
        return now_ny.date()

    return _previous_trading_day(now_ny.date())


def _read_manifest(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _write_manifest(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _needs_market_refresh(cache_dir: Path, force_refresh: bool = False) -> bool:
    if force_refresh:
        return True

    path = _manifest_file(cache_dir)
    if not path.exists():
        return True

    manifest = _read_manifest(path)
    last_session = str(manifest.get("latest_market_session_date") or "").strip()
    target_session = _current_market_session_date().isoformat()
    return last_session != target_session


def _write_market_data_manifest(
    *,
    cache_dir: Path,
    yf_symbols: List[str],
    required_start: str,
    prices: Dict[str, pd.DataFrame],
    refreshed_symbols: List[str],
    force_refresh: bool,
    market_aware_refresh: bool,
) -> None:
    latest_cache_date = None
    for frame in prices.values():
        if frame is None or frame.empty:
            continue
        frame_max = pd.Timestamp(frame.index.max()).date().isoformat()
        if latest_cache_date is None or frame_max > latest_cache_date:
            latest_cache_date = frame_max

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_source": "yfinance",
        "required_start": required_start,
        "symbol_count": len(yf_symbols),
        "symbols": sorted({str(s).strip().upper() for s in yf_symbols if str(s).strip()}),
        "latest_cache_date": latest_cache_date,
        "latest_market_session_date": _current_market_session_date().isoformat(),
        "market_aware_refresh": bool(market_aware_refresh),
        "force_refresh": bool(force_refresh),
        "refreshed_symbol_count": len(refreshed_symbols),
        "refreshed_symbols": sorted({str(s).strip().upper() for s in refreshed_symbols if str(s).strip()}),
    }
    _write_manifest(_manifest_file(cache_dir), payload)


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


def _merge_cached_with_incremental(cached: pd.DataFrame, incremental: pd.DataFrame) -> pd.DataFrame:
    if cached is None or cached.empty:
        return incremental.sort_index()
    if incremental is None or incremental.empty:
        return cached.sort_index()

    merged = pd.concat([cached, incremental], axis=0)
    merged = merged[~merged.index.duplicated(keep="last")]
    merged = merged.sort_index()
    return merged


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


def get_daily_data(symbol: str, years: int = 3) -> pd.DataFrame:
    """Fetch daily OHLCV data for a single symbol for the last `years` years."""
    safe_years = max(1, int(years))
    start = (datetime.now(timezone.utc) - timedelta(days=365 * safe_years)).date().isoformat()

    df = yf.download(
        tickers=[symbol],
        start=start,
        interval="1d",
        auto_adjust=False,
        progress=False,
        group_by="ticker",
        threads=False,
    )

    frame = _extract_symbol_frame(df, symbol)
    return frame


def fetch_prices(
    yf_symbols: List[str],
    settings: Settings,
    logger: logging.Logger,
    *,
    force_refresh: bool = False,
    market_aware_refresh: bool = True,
) -> Tuple[Dict[str, pd.DataFrame], DataDiagnostics]:
    settings.cache_path.mkdir(parents=True, exist_ok=True)

    prices: Dict[str, pd.DataFrame] = {}
    stale_symbols: List[str] = []
    skipped: List[dict] = []
    cached_symbols = 0

    start = (datetime.now(timezone.utc) - timedelta(days=settings.lookback_calendar_days)).date().isoformat()
    start_ts = pd.Timestamp(start)
    target_session = _current_market_session_date()
    refresh_all = bool(market_aware_refresh and _needs_market_refresh(settings.cache_path, force_refresh=force_refresh))

    cached_frames: Dict[str, pd.DataFrame] = {}
    append_groups: Dict[str, List[str]] = {}

    if refresh_all:
        logger.info(
            "Market-aware refresh active: refreshing symbols (force_refresh=%s) with incremental append when possible",
            force_refresh,
        )

    for symbol in yf_symbols:
        cache_path = _cache_file(settings.cache_path, symbol)
        if not cache_path.exists():
            stale_symbols.append(symbol)
            continue

        cached = _read_cached(cache_path)
        if cached.empty:
            stale_symbols.append(symbol)
            continue

        cached_frames[symbol] = cached
        cached_min = pd.Timestamp(cached.index.min())
        cached_max = pd.Timestamp(cached.index.max())

        if cached_min > start_ts:
            # Cache does not fully cover required historical window.
            stale_symbols.append(symbol)
            continue

        if force_refresh:
            stale_symbols.append(symbol)
            continue

        if refresh_all:
            if cached_max.date() < target_session:
                append_start = (cached_max + timedelta(days=1)).date().isoformat()
                append_groups.setdefault(append_start, []).append(symbol)
                continue
            prices[symbol] = cached
            cached_symbols += 1
            continue

        if _is_fresh(cache_path, settings.cache_max_age_days, required_start=start):
            prices[symbol] = cached
            cached_symbols += 1
            continue

        stale_symbols.append(symbol)

    refreshed_symbols: List[str] = []
    downloaded_symbols = 0

    # Incremental append path (only missing tail bars after last cached date).
    for append_start, symbols_to_append in append_groups.items():
        for i in range(0, len(symbols_to_append), settings.download_batch_size):
            chunk = symbols_to_append[i : i + settings.download_batch_size]
            if not chunk:
                continue
            try:
                df = yf.download(
                    tickers=chunk,
                    start=append_start,
                    interval="1d",
                    auto_adjust=False,
                    progress=False,
                    group_by="ticker",
                    threads=True,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed incremental yfinance download for %s", chunk)
                for symbol in chunk:
                    skipped.append({"yf_symbol": symbol, "reason": f"incremental_download_error:{exc.__class__.__name__}"})
                    cached = cached_frames.get(symbol)
                    if cached is not None and not cached.empty:
                        prices[symbol] = cached
                        cached_symbols += 1
                continue

            for symbol in chunk:
                cached = cached_frames.get(symbol)
                if cached is None or cached.empty:
                    stale_symbols.append(symbol)
                    continue

                frame = _extract_symbol_frame(df, symbol)
                merged = _merge_cached_with_incremental(cached, frame)
                prices[symbol] = merged
                _write_cache(_cache_file(settings.cache_path, symbol), merged)

                if frame.empty:
                    cached_symbols += 1
                else:
                    downloaded_symbols += 1
                    refreshed_symbols.append(symbol)

    # Full-refresh path (new symbols, force refresh, or insufficient history coverage).
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
            refreshed_symbols.append(symbol)
            _write_cache(_cache_file(settings.cache_path, symbol), frame)

    _write_market_data_manifest(
        cache_dir=settings.cache_path,
        yf_symbols=yf_symbols,
        required_start=start,
        prices=prices,
        refreshed_symbols=refreshed_symbols,
        force_refresh=force_refresh,
        market_aware_refresh=market_aware_refresh,
    )

    diagnostics = DataDiagnostics(
        downloaded_symbols=downloaded_symbols,
        cached_symbols=cached_symbols,
        skipped=skipped,
    )
    return prices, diagnostics
