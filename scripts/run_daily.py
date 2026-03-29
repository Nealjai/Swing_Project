from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from screener.config import Settings
from screener.data import fetch_prices
from screener.engines import bull_candidates, weak_candidates
from screener.export import export_outputs
from screener.indicators import add_indicators, latest_metrics
from screener.ranking import rank_candidates
from screener.regime import detect_regime
from screener.universe import UniverseItem, load_universe


def setup_logger() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    return logging.getLogger("screener")


def _build_rows(
    items: List[UniverseItem],
    enriched: Dict[str, object],
    logger: logging.Logger,
) -> List[Dict]:
    rows: List[Dict] = []
    for item in items:
        df = enriched.get(item.yf_symbol)
        if df is None:
            continue
        try:
            metrics = latest_metrics(df)
            row = {
                "symbol": item.symbol,
                "yf_symbol": item.yf_symbol,
                **metrics,
            }
            rows.append(row)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping %s while building metrics: %s", item.symbol, exc)
    return rows


def main() -> int:
    settings = Settings()
    logger = setup_logger()

    universe = load_universe(settings.universe_file)
    yf_symbols = sorted({u.yf_symbol for u in universe})
    if settings.benchmark_symbol not in yf_symbols:
        yf_symbols.append(settings.benchmark_symbol)

    prices, data_diag = fetch_prices(yf_symbols=yf_symbols, settings=settings, logger=logger)

    benchmark_df = prices.get(settings.benchmark_symbol)
    if benchmark_df is None or benchmark_df.empty:
        logger.error("Benchmark %s data unavailable, aborting", settings.benchmark_symbol)
        return 1

    enriched: Dict[str, object] = {}
    skipped = list(data_diag.skipped)

    benchmark_enriched = add_indicators(
        benchmark_df,
        breakout_lookback=settings.breakout_lookback,
        rsi_length=settings.rsi_length,
        bb_length=settings.bb_length,
        bb_std=settings.bb_std,
        sma_regime_length=settings.sma_regime_length,
    )
    if benchmark_enriched.empty or benchmark_enriched["sma200"].dropna().empty:
        logger.error("Benchmark %s lacks enough history for SMA200", settings.benchmark_symbol)
        return 1

    enriched[settings.benchmark_symbol] = benchmark_enriched

    for item in universe:
        raw = prices.get(item.yf_symbol)
        if raw is None or raw.empty:
            skipped.append({"symbol": item.symbol, "yf_symbol": item.yf_symbol, "reason": "missing_price_data"})
            continue

        try:
            e = add_indicators(
                raw,
                breakout_lookback=settings.breakout_lookback,
                rsi_length=settings.rsi_length,
                bb_length=settings.bb_length,
                bb_std=settings.bb_std,
                sma_regime_length=settings.sma_regime_length,
            )
            if e.empty or len(e) < max(settings.sma_regime_length, settings.bb_length, settings.breakout_lookback):
                skipped.append({"symbol": item.symbol, "yf_symbol": item.yf_symbol, "reason": "insufficient_history"})
                continue
            enriched[item.yf_symbol] = e
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping %s due to indicator error: %s", item.symbol, exc)
            skipped.append(
                {
                    "symbol": item.symbol,
                    "yf_symbol": item.yf_symbol,
                    "reason": f"indicator_error:{exc.__class__.__name__}",
                }
            )

    regime = detect_regime(benchmark_enriched)
    rows = _build_rows(universe, enriched, logger)

    if regime.regime == "bull":
        raw_candidates = bull_candidates(
            rows,
            min_price=settings.min_price,
            min_avg_dollar_volume=settings.min_avg_dollar_volume,
        )
        engine_name = "bull"
    else:
        raw_candidates = weak_candidates(
            rows,
            min_price=settings.min_price,
            min_avg_dollar_volume=settings.min_avg_dollar_volume,
            weak_rsi_threshold=settings.weak_rsi_threshold,
        )
        engine_name = "weak"

    ranked = rank_candidates(raw_candidates, settings.max_candidates)

    diagnostics = {
        "downloaded_symbols": data_diag.downloaded_symbols,
        "cached_symbols": data_diag.cached_symbols,
        "missing_or_skipped_count": len(skipped),
        "skipped": skipped,
        "rows_with_metrics": len(rows),
    }

    benchmark_snapshot = {
        "symbol": settings.benchmark_symbol,
        "close": regime.benchmark_close,
        "sma200": regime.benchmark_sma200,
        "above_sma200": regime.benchmark_above_sma200,
    }

    export_outputs(
        settings_snapshot=settings.snapshot(),
        benchmark=benchmark_snapshot,
        candidates=ranked,
        diagnostics=diagnostics,
        regime=regime.regime,
        engine=engine_name,
        universe_size=len(universe),
        json_path=settings.output_json,
        csv_path=settings.output_csv,
    )

    logger.info(
        "Finished run: regime=%s engine=%s candidates=%s universe=%s",
        regime.regime,
        engine_name,
        len(ranked),
        len(universe),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
