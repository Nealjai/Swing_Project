from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd


def compute_rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(length).mean()


def add_indicators(
    df: pd.DataFrame,
    breakout_lookback: int,
    rsi_length: int,
    bb_length: int,
    bb_std: float,
    sma_regime_length: int,
) -> pd.DataFrame:
    out = df.copy()

    # Use adjusted close for signal indicators when available.
    signal_close = out["Adj Close"] if "Adj Close" in out.columns else out["Close"]
    out["signal_close"] = signal_close

    out["ema9"] = signal_close.ewm(span=9, adjust=False).mean()
    out["ema21"] = signal_close.ewm(span=21, adjust=False).mean()
    out["sma20"] = signal_close.rolling(20).mean()
    out["sma50"] = signal_close.rolling(50).mean()
    out["sma200"] = signal_close.rolling(sma_regime_length).mean()

    out["high_20d"] = signal_close.rolling(breakout_lookback).max()
    out["rsi14"] = compute_rsi(signal_close, rsi_length)

    bb_mid = signal_close.rolling(bb_length).mean()
    bb_sigma = signal_close.rolling(bb_length).std(ddof=0)
    out["bb_mid"] = bb_mid
    out["bb_upper"] = bb_mid + bb_std * bb_sigma
    out["bb_lower"] = bb_mid - bb_std * bb_sigma

    out["atr14"] = compute_atr(out["High"], out["Low"], out["Close"], length=14)

    out["dollar_volume"] = out["Close"] * out["Volume"]
    out["avg_dollar_volume_20d"] = out["dollar_volume"].rolling(20).mean()

    return out


def latest_metrics(df: pd.DataFrame) -> Dict[str, float]:
    row = df.iloc[-1]
    return {
        "close": float(row.get("Close", np.nan)),
        "adj_close": float(row.get("signal_close", np.nan)),
        "volume": float(row.get("Volume", np.nan)),
        "high_20d": float(row.get("high_20d", np.nan)),
        "rsi14": float(row.get("rsi14", np.nan)),
        "bb_upper": float(row.get("bb_upper", np.nan)),
        "bb_lower": float(row.get("bb_lower", np.nan)),
        "sma20": float(row.get("sma20", np.nan)),
        "sma50": float(row.get("sma50", np.nan)),
        "sma200": float(row.get("sma200", np.nan)),
        "ema9": float(row.get("ema9", np.nan)),
        "ema21": float(row.get("ema21", np.nan)),
        "atr14": float(row.get("atr14", np.nan)),
        "avg_dollar_volume_20d": float(row.get("avg_dollar_volume_20d", np.nan)),
    }
