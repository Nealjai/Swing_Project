from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

SPY_SYMBOL = "SPY"
VIX_SYMBOL = "^VIX"
SPY_LOOKBACK_DAYS = 2000
VIX_LOOKBACK_DAYS = 30
ROLLING_DD_WINDOW = 25


@dataclass(frozen=True)
class MarketSignals:
    spy_close_above_sma200: bool
    spy_close_above_sma50: bool
    sma50_up_10d: bool


def _num(value: float | int | np.floating | np.integer | None) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except Exception:  # noqa: BLE001
        return None
    if np.isnan(out) or np.isinf(out):
        return None
    return out


def _download_history(symbol: str, lookback_days: int) -> pd.DataFrame:
    """Download and normalize daily OHLCV data for a single symbol."""
    start = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).date().isoformat()
    raw = yf.download(
        tickers=symbol,
        start=start,
        interval="1d",
        auto_adjust=False,
        progress=False,
        group_by="ticker",
        threads=False,
    )

    if raw is None or raw.empty:
        return pd.DataFrame()

    if isinstance(raw.columns, pd.MultiIndex):
        if symbol in raw.columns.get_level_values(0):
            raw = raw[symbol]

    required_cols = ["Open", "High", "Low", "Close", "Volume"]
    if any(col not in raw.columns for col in required_cols):
        return pd.DataFrame()

    out = raw[required_cols].copy().dropna(subset=["Close"]).sort_index()
    out.index = pd.to_datetime(out.index)
    return out


def _add_spy_indicators(spy_df: pd.DataFrame) -> pd.DataFrame:
    out = spy_df.copy()
    out["sma50"] = out["Close"].rolling(50).mean()
    out["sma200"] = out["Close"].rolling(200).mean()
    out["sma50_dir_10d"] = (out["sma50"] / out["sma50"].shift(10)) - 1.0
    out["daily_return"] = out["Close"].pct_change()
    return out


def _calculate_regime_signals(spy_df: pd.DataFrame) -> MarketSignals:
    latest = spy_df.iloc[-1]
    return MarketSignals(
        spy_close_above_sma200=bool(latest["Close"] > latest["sma200"]),
        spy_close_above_sma50=bool(latest["Close"] > latest["sma50"]),
        sma50_up_10d=bool(latest["sma50"] > spy_df["sma50"].iloc[-11]),
    )


def _determine_regime(signals: MarketSignals) -> str:
    bullish_votes = sum(
        [
            signals.spy_close_above_sma200,
            signals.spy_close_above_sma50,
            signals.sma50_up_10d,
        ]
    )

    if bullish_votes == 3:
        return "Bull"
    if bullish_votes == 0:
        return "Bear"
    return "Choppy"


def _distribution_days(spy_df: pd.DataFrame) -> Tuple[pd.Series, List[Dict[str, float | str]]]:
    down_enough = spy_df["daily_return"] <= -0.002
    higher_volume = spy_df["Volume"] > spy_df["Volume"].shift(1)
    is_distribution_day = down_enough & higher_volume

    dd_rolling_count = is_distribution_day.rolling(ROLLING_DD_WINDOW, min_periods=1).sum().astype(int)

    markers: List[Dict[str, float | str]] = []
    dd_rows = spy_df[is_distribution_day.fillna(False)]
    for dt, row in dd_rows.iterrows():
        close = _num(row.get("Close"))
        if close is None:
            continue
        markers.append({"date": dt.strftime("%Y-%m-%d"), "price": close})

    return dd_rolling_count, markers


def _follow_through_days(spy_df: pd.DataFrame) -> List[Dict[str, float | str]]:
    """
    Detect follow-through days (FTD) from rally attempts.

    Rules implemented:
    - A rally attempt starts on an up-close day.
    - FTD can occur on day 4 or later of that attempt.
    - FTD day must gain >= 1.25% and close on higher volume than prior day.
    - Rally attempt is invalidated if price undercuts rally low.
    """
    if len(spy_df) < 5:
        return []

    markers: List[Dict[str, float | str]] = []

    in_attempt = False
    attempt_start_idx = -1
    rally_low = np.inf

    for i in range(1, len(spy_df)):
        prev_close = _num(spy_df["Close"].iloc[i - 1])
        prev_volume = _num(spy_df["Volume"].iloc[i - 1])
        close = _num(spy_df["Close"].iloc[i])
        low = _num(spy_df["Low"].iloc[i])
        volume = _num(spy_df["Volume"].iloc[i])

        if prev_close is None or prev_volume is None or close is None or low is None or volume is None:
            continue

        dt = spy_df.index[i].strftime("%Y-%m-%d")
        is_up_day = close > prev_close

        # Start a new rally attempt on the first up day.
        if not in_attempt and is_up_day:
            in_attempt = True
            attempt_start_idx = i
            rally_low = low
            continue

        if not in_attempt:
            continue

        day_of_attempt = i - attempt_start_idx + 1

        # Invalidate rally if low undercuts the attempt low.
        if low < rally_low:
            in_attempt = False
            attempt_start_idx = -1
            rally_low = np.inf

            # A fresh up day can immediately start a new rally attempt.
            if is_up_day:
                in_attempt = True
                attempt_start_idx = i
                rally_low = low
            continue

        rally_low = min(rally_low, low)
        gain_pct = (close / prev_close) - 1.0
        higher_volume = volume > prev_volume

        if day_of_attempt >= 4 and gain_pct >= 0.0125 and higher_volume:
            markers.append(
                {
                    "date": dt,
                    "price": close,
                }
            )
            # Only one FTD marker per attempt.
            in_attempt = False
            attempt_start_idx = -1
            rally_low = np.inf

    return markers


def _series_to_list(series: pd.Series) -> List[float | None]:
    return [_num(v) for v in series.tolist()]


def get_market_condition() -> Dict[str, object]:
    """
    Build market condition payload for backend and charting.

    Returns a dictionary that includes:
    - SPY historical OHLCV and indicators.
    - Current market regime label.
    - Current VIX close.
    - Distribution day / follow-through day markers.
    - Rolling 25-day distribution day count.
    """
    spy_df = _download_history(SPY_SYMBOL, SPY_LOOKBACK_DAYS)
    vix_df = _download_history(VIX_SYMBOL, VIX_LOOKBACK_DAYS)

    if spy_df.empty:
        raise ValueError("SPY history is unavailable")
    if vix_df.empty:
        raise ValueError("VIX history is unavailable")

    spy_df = _add_spy_indicators(spy_df)
    valid_spy = spy_df.dropna(subset=["sma50", "sma200"])

    if len(valid_spy) < 11:
        raise ValueError("Not enough SPY history to compute 10-day SMA50 direction")

    signals = _calculate_regime_signals(valid_spy)
    regime_label = _determine_regime(signals)

    dd_rolling_count, distribution_day_markers = _distribution_days(valid_spy)
    ftd_markers = _follow_through_days(valid_spy)

    dates = [dt.strftime("%Y-%m-%d") for dt in valid_spy.index]
    result: Dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "regime_label": regime_label,
        "signals": {
            "spy_close_above_sma200": signals.spy_close_above_sma200,
            "spy_close_above_sma50": signals.spy_close_above_sma50,
            "sma50_up_10d": signals.sma50_up_10d,
        },
        "spy_close": _num(valid_spy["Close"].iloc[-1]),
        "vix_close": _num(vix_df["Close"].iloc[-1]),
        "distribution_day_count_25d": int(dd_rolling_count.iloc[-1]),
        "distribution_day_count_25d_series": dd_rolling_count.astype(int).tolist(),
        "distribution_day_dates": [m["date"] for m in distribution_day_markers],
        "follow_through_day_dates": [m["date"] for m in ftd_markers],
        "chart_markers": {
            "distribution_days": distribution_day_markers,
            "follow_through_days": ftd_markers,
        },
        "spy_history": {
            "dates": dates,
            "open": _series_to_list(valid_spy["Open"]),
            "high": _series_to_list(valid_spy["High"]),
            "low": _series_to_list(valid_spy["Low"]),
            "close": _series_to_list(valid_spy["Close"]),
            "volume": _series_to_list(valid_spy["Volume"]),
            "sma50": _series_to_list(valid_spy["sma50"]),
            "sma200": _series_to_list(valid_spy["sma200"]),
        },
    }
    return result
