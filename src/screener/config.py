from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass(frozen=True)
class Settings:
    universe_file: str = "universe.txt"
    benchmark_symbol: str = "SPY"
    lookback_calendar_days: int = 760
    cache_dir: str = "data/cache"
    cache_max_age_days: int = 1
    download_batch_size: int = 100
    yfinance_max_retries: int = 2

    ticker_info_max_workers: int = 16
    ticker_info_cache_max_age_days: int = 7

    min_price: float = 5.0
    min_market_cap: float = 3_000_000_000.0
    min_beta_1y: float = 1.0
    min_volume: float = 500_000.0
    min_avg_dollar_volume_20d: float = 20_000_000.0
    min_avg_dollar_volume_20d_bull: float = 30_000_000.0
    min_avg_dollar_volume_20d_choppy: float = 75_000_000.0
    min_avg_dollar_volume_20d_bear: float = 100_000_000.0
    min_atr_dollars: float = 0.50
    atr_pct_tier_lt_20: float = 0.12
    atr_pct_tier_20_to_100: float = 0.10
    atr_pct_tier_gt_100: float = 0.08
    max_atr_pct: float = 0.08

    sma_regime_length: int = 200
    breakout_lookback: int = 20
    rsi_length: int = 14
    bb_length: int = 20
    bb_std: float = 2.0
    weak_rsi_threshold: float = 30.0

    initial_capital: float = 10_000.0
    max_positions: int = 6
    max_position_exposure_pct: float = 0.25
    risk_per_trade_bull: float = 0.005
    risk_per_trade_choppy: float = 0.0025
    risk_per_trade_bear: float = 0.001
    monthly_drawdown_soft: float = 0.03
    monthly_drawdown_hard: float = 0.06

    max_candidates: int = 50

    output_json: str = "docs/data/latest.json"
    output_csv: str = "docs/data/latest.csv"

    def snapshot(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def cache_path(self) -> Path:
        return Path(self.cache_dir)
