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


def add_indicators(
    df: pd.DataFrame,
    breakout_lookback: int,
    rsi_length: int,
    bb_length: int,
    bb_std: float,
    sma_regime_length: int,
) -> pd.DataFrame:
    out = df.copy()
    close = out["Close"]

    out["sma200"] = close.rolling(sma_regime_length).mean()
    out["high_20d"] = out["High"].rolling(breakout_lookback).max()
    out["rsi14"] = compute_rsi(close, rsi_length)

    bb_mid = close.rolling(bb_length).mean()
    bb_sigma = close.rolling(bb_length).std(ddof=0)
    out["bb_mid"] = bb_mid
    out["bb_upper"] = bb_mid + bb_std * bb_sigma
    out["bb_lower"] = bb_mid - bb_std * bb_sigma

    out["dollar_volume"] = out["Close"] * out["Volume"]
    out["avg_dollar_volume_20d"] = out["dollar_volume"].rolling(20).mean()

    return out


def latest_metrics(df: pd.DataFrame) -> Dict[str, float]:
    row = df.iloc[-1]
    return {
        "close": float(row.get("Close", np.nan)),
        "high_20d": float(row.get("high_20d", np.nan)),
        "rsi14": float(row.get("rsi14", np.nan)),
        "bb_upper": float(row.get("bb_upper", np.nan)),
        "bb_lower": float(row.get("bb_lower", np.nan)),
        "sma200": float(row.get("sma200", np.nan)),
        "avg_dollar_volume_20d": float(row.get("avg_dollar_volume_20d", np.nan)),
    }
