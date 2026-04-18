from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass(frozen=True)
class Settings:
    universe_file: str = "sp500.txt"
    benchmark_symbol: str = "SPY"
    lookback_calendar_days: int = 760
    cache_dir: str = "data/cache"
    cache_max_age_days: int = 1
    download_batch_size: int = 100

    min_price: float = 5.0
    min_market_cap: float = 3_000_000_000.0
    min_beta_1y: float = 1.0
    min_volume: float = 500_000.0
    min_avg_dollar_volume_20d: float = 20_000_000.0

    sma_regime_length: int = 200
    breakout_lookback: int = 20
    rsi_length: int = 14
    bb_length: int = 20
    bb_std: float = 2.0
    weak_rsi_threshold: float = 30.0

    max_candidates: int = 50

    output_json: str = "docs/data/latest.json"
    output_csv: str = "docs/data/latest.csv"

    def snapshot(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def cache_path(self) -> Path:
        return Path(self.cache_dir)
