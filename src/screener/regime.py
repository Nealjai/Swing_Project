from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class RegimeResult:
    regime: str
    benchmark_close: float
    benchmark_sma200: float
    benchmark_above_sma200: bool


def detect_regime(benchmark_df: pd.DataFrame) -> RegimeResult:
    latest = benchmark_df.iloc[-1]
    close = float(latest["Close"])
    sma200 = float(latest["sma200"])
    is_bull = close > sma200
    return RegimeResult(
        regime="bull" if is_bull else "weak",
        benchmark_close=close,
        benchmark_sma200=sma200,
        benchmark_above_sma200=is_bull,
    )
