from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from screener.backtest.engine import BacktestConfig, run_backtest
from screener.backtest.output import (
    build_summary_payload,
    format_summary_table,
    write_summary_json,
    write_run_config_json,
    write_summary_history_json,
    write_symbols_json,
    write_trade_log,
    write_candidates_csv,
    write_backtest_runs_index_json,
)
from screener.backtest.portfolio import PortfolioConfig, simulate_portfolio
from screener.backtest.stats import summarize_trades
from screener.config import Settings
from screener.data import fetch_prices
from screener.universe import load_universe

TEST_SYMBOLS_21 = [
    # Technology
    "AAPL",
    "MSFT",
    "NVDA",
    # Communication Services
    "GOOGL",
    "META",
    "NFLX",
    # Consumer Discretionary
    "AMZN",
    "TSLA",
    "HD",
    # Health Care
    "LLY",
    "JNJ",
    "UNH",
    # Financials
    "JPM",
    "BAC",
    "GS",
    # Industrials
    "CAT",
    "HON",
    "GE",
    # Energy
    "XOM",
    "CVX",
    "SLB",
]


def setup_logger() -> logging.Logger:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    return logging.getLogger("backtest")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run dual-engine swing screener backtest")
    parser.add_argument("--engine", choices=["bull", "weak", "both"], default="both")
    parser.add_argument("--start-date", default=None, help="Backtest start date (YYYY-MM-DD). If omitted, derived from --years.")
    parser.add_argument("--end-date", default=None, help="Backtest end date (YYYY-MM-DD). If omitted, defaults to today (UTC date).")
    parser.add_argument("--years", type=int, default=10, help="Convenience lookback window in years when --start-date is omitted.")
    parser.add_argument(
        "--symbol-mode",
        choices=["test", "full"],
        default="full",
        help="Universe mode: 'full' uses universe file (default sp500.txt), 'test' uses the 21-symbol smoke-test list.",
    )
    parser.add_argument("--universe-file", default="sp500.txt", help="Universe text file path (one ticker per line)")
    parser.add_argument("--benchmark-symbol", default="SPY", help="Benchmark symbol used for regime filter/calendar")

    # Human-readable run metadata
    parser.add_argument("--run-name", default=None, help="Optional descriptive run title")
    parser.add_argument("--run-description", default=None, help="Optional longer run description")

    # Portfolio simulator assumptions
    parser.add_argument("--initial-capital", type=float, default=10000.0)
    parser.add_argument("--max-positions", type=int, default=10)
    parser.add_argument("--slippage-pct", type=float, default=0.0005)
    parser.add_argument("--commission-per-side", type=float, default=0.32)
    parser.add_argument("--monthly-dd-limit-pct", type=float, default=6.0)
    parser.add_argument("--monthly-risk-per-trade-pct", type=float, default=1.0)
    parser.add_argument("--risk-free-rate-annual", type=float, default=0.0)
    parser.add_argument("--trading-days-per-year", type=int, default=252)

    # Data refresh behavior
    parser.add_argument("--force-refresh", action="store_true", help="Force refresh of all cached market data")
    parser.add_argument(
        "--disable-market-aware-refresh",
        action="store_true",
        help="Disable daily market-session-aware refresh logic and rely only on cache freshness rules",
    )

    # Output/run history behavior
    parser.add_argument("--run-id", default=None, help="Optional run identifier for run history files")

    # Scenario re-run behavior
    parser.add_argument(
        "--reuse-candidates-csv",
        default=None,
        help="Reuse candidates from a previous run and re-run only portfolio simulation",
    )

    return parser.parse_args()


def _lookback_days(start_date: str, end_date: str, warmup_days: int = 260) -> int:
    """Compute download lookback from *today* so historical windows are not truncated.

    fetch_prices() downloads from (now - lookback_days), so for historical backtests
    we must ensure lookback reaches at least start_date + warmup from today's date,
    not merely (end_date - start_date).
    """
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    now = datetime.now()

    # Backtest period length (legacy minimum baseline).
    span_days = max(0, (end - start).days)
    # Distance from today back to requested start date.
    days_to_start = max(0, (now - start).days)

    required = max(span_days, days_to_start) + warmup_days
    return max(800, int(required))


def _resolve_backtest_window(start_date: str | None, end_date: str | None, years: int) -> tuple[str, str]:
    today = datetime.now(timezone.utc).date()

    if end_date:
        resolved_end = datetime.strptime(str(end_date), "%Y-%m-%d").date()
    else:
        resolved_end = today

    if start_date:
        resolved_start = datetime.strptime(str(start_date), "%Y-%m-%d").date()
    else:
        safe_years = max(1, int(years))
        resolved_start = resolved_end - timedelta(days=int(round(365.25 * safe_years)))

    if resolved_start > resolved_end:
        raise ValueError("start_date must be on or before end_date")

    return resolved_start.isoformat(), resolved_end.isoformat()



def _resolve_symbols(settings: Settings, symbol_mode: str) -> List[str]:
    if symbol_mode == "test":
        return sorted({s.strip().upper() for s in TEST_SYMBOLS_21 if s.strip()})
    universe = load_universe(settings.universe_file)
    return sorted({item.yf_symbol for item in universe})


def _portfolio_assumptions_dict(config: PortfolioConfig) -> Dict[str, object]:
    return {
        "initial_capital": config.initial_capital,
        "max_positions": config.max_positions,
        "slippage_pct_each_side": config.slippage_pct_each_side,
        "commission_per_side": config.commission_per_side,
        "monthly_drawdown_limit_pct": config.monthly_drawdown_limit_pct,
        "monthly_risk_per_trade_pct": config.monthly_risk_per_trade_pct,
        "risk_free_rate_annual": config.risk_free_rate_annual,
        "trading_days_per_year": config.trading_days_per_year,
        "share_rounding": config.share_rounding,
        "entry_priority": config.entry_priority,
        "monthly_drawdown_rule": "halt_new_entries_if_equity_below_month_start_equity_threshold",
    }


def _build_methodology_meta(config: PortfolioConfig) -> Dict[str, object]:
    return {
        "entry_rules": "Signals generated by bull/weak engines; entries at next session open when signal date regime matches engine.",
        "exit_rules": "Gap-aware execution: SL/TP can trigger at open on gap-through, otherwise intraday High/Low checks for TP/SL, else planned exit date close fallback.",
        "signal_triggers": {
            "bull_engine": "In bull regime, signal when close is near 20-day breakout level (close >= high_20d * 0.995) and liquidity/fundamental filters pass.",
            "weak_engine": "In weak regime, signal when close <= lower Bollinger Band and RSI14 <= weak threshold, with liquidity/fundamental filters pass.",
            "common_filters": "min_price, min_volume, min_avg_dollar_volume_20d, min_market_cap, min_beta_1y",
        },
        "regime_filter_logic": "Regime filter uses SPY vs SMA200: Bull engine above SMA200, Weak engine below SMA200.",
        "next_open_entry": "Enabled",
        "signal_price_vs_pnl_price": "Signals use adjusted-close indicators; portfolio fills use raw OHLC with slippage and commissions.",
        "intraday_exit_priority": "If both SL and TP touch intraday on same bar, stop-loss is prioritized (conservative assumption).",
        "metric_definitions": {
            "overall_return_pct": "((final_equity / initial_capital) - 1) * 100",
            "cagr_pct": "((final_equity / initial_capital)^(1/years) - 1) * 100, where years = elapsed_days / 365.25",
            "benchmark_total_return_pct": "SPY buy-and-hold over same period using Adj Close when available",
            "benchmark_cagr_pct": "SPY CAGR over same period using elapsed_days / 365.25",
            "outperformance_delta_pct": "strategy_metric_pct - benchmark_metric_pct",
        },
        "portfolio_assumptions": _portfolio_assumptions_dict(config),
    }


def _build_diagnostics_summary(
    *,
    candidates: pd.DataFrame,
    executed_trades: pd.DataFrame,
    fills_log: pd.DataFrame,
) -> Dict[str, object]:
    total_candidates = int(len(candidates)) if candidates is not None else 0
    trades_taken = int(len(executed_trades)) if executed_trades is not None else 0

    rejected = pd.DataFrame()
    if fills_log is not None and not fills_log.empty and "status" in fills_log.columns:
        rejected = fills_log[fills_log["status"] == "rejected"].copy()

    rejected_entries = int(len(rejected))
    acceptance_rate = (float(trades_taken) / float(total_candidates) * 100.0) if total_candidates > 0 else None
    rejection_rate = (float(rejected_entries) / float(total_candidates) * 100.0) if total_candidates > 0 else None

    top_rejection_reasons: List[Dict[str, object]] = []
    if not rejected.empty and "reason" in rejected.columns:
        reason_counts = (
            rejected["reason"]
            .fillna("unknown")
            .astype(str)
            .value_counts(dropna=False)
            .head(8)
        )
        top_rejection_reasons = [
            {"reason": str(reason), "count": int(count)} for reason, count in reason_counts.items()
        ]

    return {
        "summary": {
            "total_candidates": total_candidates,
            "trades_taken": trades_taken,
            "rejected_entries": rejected_entries,
            "acceptance_rate_pct": round(acceptance_rate, 4) if acceptance_rate is not None else None,
            "rejection_rate_pct": round(rejection_rate, 4) if rejection_rate is not None else None,
        },
        "top_rejection_reasons": top_rejection_reasons,
    }


def _build_run_config(
    *,
    args: argparse.Namespace,
    symbols: List[str],
    benchmark_symbol: str,
    portfolio_cfg: PortfolioConfig,
    lookback_calendar_days: int,
    start_date: str,
    end_date: str,
    years: int,
) -> Dict[str, object]:
    market_aware_refresh = not bool(args.disable_market_aware_refresh)
    run_name = (str(args.run_name).strip() if args.run_name else "") or f"{args.engine.upper()} | {args.symbol_mode.upper()} | {start_date}→{end_date}"
    run_description = (
        str(args.run_description).strip()
        if args.run_description
        else (
            f"Backtest using engine={args.engine}, universe={args.symbol_mode} ({len(symbols)} symbols), "
            f"period={start_date}..{end_date}, benchmark={benchmark_symbol}."
        )
    )

    return {
        "run_name": run_name,
        "run_description": run_description,
        "engine": args.engine,
        "date_range": {
            "start_date": start_date,
            "end_date": end_date,
            "lookback_years": int(max(1, years)),
            "warmup_bars": 200,
            "lookback_calendar_days": int(lookback_calendar_days),
        },
        "universe": {
            "symbol_mode": args.symbol_mode,
            "symbol_count": int(len(symbols)),
            "universe_file": args.universe_file,
            "benchmark_symbol": benchmark_symbol,
        },
        "portfolio": _portfolio_assumptions_dict(portfolio_cfg),
        "data_refresh": {
            "force_refresh": bool(args.force_refresh),
            "market_aware_refresh": bool(market_aware_refresh),
        },
        "user_inputs": {
            "engine": args.engine,
            "start_date": start_date,
            "end_date": end_date,
            "years": int(max(1, years)),
            "symbol_mode": args.symbol_mode,
            "universe_file": args.universe_file,
            "benchmark_symbol": benchmark_symbol,
            "initial_capital": float(args.initial_capital),
            "max_positions": int(args.max_positions),
            "slippage_pct": float(args.slippage_pct),
            "commission_per_side": float(args.commission_per_side),
            "monthly_dd_limit_pct": float(args.monthly_dd_limit_pct),
            "monthly_risk_per_trade_pct": float(args.monthly_risk_per_trade_pct),
            "risk_free_rate_annual": float(args.risk_free_rate_annual),
            "trading_days_per_year": int(args.trading_days_per_year),
            "force_refresh": bool(args.force_refresh),
            "market_aware_refresh": bool(market_aware_refresh),
            "run_name": run_name,
            "run_description": run_description,
        },
    }


def _compute_spy_benchmark_metrics(
    *,
    prices_by_symbol: Dict[str, pd.DataFrame],
    benchmark_symbol: str,
    start_date: str,
    end_date: str,
    strategy_total_return_pct: float | None,
    strategy_cagr_pct: float | None,
) -> Dict[str, object]:
    benchmark_df = prices_by_symbol.get(benchmark_symbol)
    if benchmark_df is None or benchmark_df.empty:
        return {
            "symbol": benchmark_symbol,
            "price_basis": None,
            "start_date_used": None,
            "end_date_used": None,
            "start_price": None,
            "end_price": None,
            "total_return_pct": None,
            "cagr_pct": None,
            "strategy_minus_benchmark_total_return_pct": None,
            "strategy_minus_benchmark_cagr_pct": None,
            "available": False,
            "reason": "missing_benchmark_data",
        }

    price_col = "Adj Close" if "Adj Close" in benchmark_df.columns else "Close"
    series = pd.to_numeric(benchmark_df[price_col], errors="coerce").dropna()
    if series.empty:
        return {
            "symbol": benchmark_symbol,
            "price_basis": price_col,
            "start_date_used": None,
            "end_date_used": None,
            "start_price": None,
            "end_price": None,
            "total_return_pct": None,
            "cagr_pct": None,
            "strategy_minus_benchmark_total_return_pct": None,
            "strategy_minus_benchmark_cagr_pct": None,
            "available": False,
            "reason": "empty_benchmark_series",
        }

    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)
    window = series[(series.index >= start_ts) & (series.index <= end_ts)]
    if window.empty:
        return {
            "symbol": benchmark_symbol,
            "price_basis": price_col,
            "start_date_used": None,
            "end_date_used": None,
            "start_price": None,
            "end_price": None,
            "total_return_pct": None,
            "cagr_pct": None,
            "strategy_minus_benchmark_total_return_pct": None,
            "strategy_minus_benchmark_cagr_pct": None,
            "available": False,
            "reason": "no_benchmark_data_in_range",
        }

    start_price = float(window.iloc[0])
    end_price = float(window.iloc[-1])
    first_date = pd.Timestamp(window.index[0])
    last_date = pd.Timestamp(window.index[-1])
    days = int((last_date - first_date).days)

    total_return_pct = None
    if start_price > 0 and end_price > 0:
        total_return_pct = ((end_price / start_price) - 1.0) * 100.0

    cagr_pct = None
    years = days / 365.25 if days > 0 else 0.0
    if total_return_pct is not None and years > 0:
        cagr_pct = ((end_price / start_price) ** (1.0 / years) - 1.0) * 100.0

    delta_total = None
    if strategy_total_return_pct is not None and total_return_pct is not None:
        delta_total = float(strategy_total_return_pct) - float(total_return_pct)

    delta_cagr = None
    if strategy_cagr_pct is not None and cagr_pct is not None:
        delta_cagr = float(strategy_cagr_pct) - float(cagr_pct)

    return {
        "symbol": benchmark_symbol,
        "price_basis": price_col,
        "start_date_used": first_date.strftime("%Y-%m-%d"),
        "end_date_used": last_date.strftime("%Y-%m-%d"),
        "start_price": round(start_price, 6),
        "end_price": round(end_price, 6),
        "total_return_pct": round(total_return_pct, 4) if total_return_pct is not None else None,
        "cagr_pct": round(cagr_pct, 4) if cagr_pct is not None else None,
        "strategy_minus_benchmark_total_return_pct": round(delta_total, 4) if delta_total is not None else None,
        "strategy_minus_benchmark_cagr_pct": round(delta_cagr, 4) if delta_cagr is not None else None,
        "available": True,
        "reason": None,
    }


def main() -> int:
    args = parse_args()
    logger = setup_logger()

    resolved_start_date, resolved_end_date = _resolve_backtest_window(args.start_date, args.end_date, args.years)

    settings = Settings()
    backtest_settings = replace(
        settings,
        universe_file=str(args.universe_file),
        benchmark_symbol=str(args.benchmark_symbol).strip().upper(),
        lookback_calendar_days=_lookback_days(resolved_start_date, resolved_end_date),
    )

    symbols = _resolve_symbols(backtest_settings, args.symbol_mode)
    config = BacktestConfig(
        start_date=resolved_start_date,
        end_date=resolved_end_date,
        engine=args.engine,
        warmup_bars=200,
    )

    portfolio_cfg = PortfolioConfig(
        initial_capital=float(args.initial_capital),
        max_positions=int(args.max_positions),
        slippage_pct_each_side=float(args.slippage_pct),
        commission_per_side=float(args.commission_per_side),
        monthly_drawdown_limit_pct=float(args.monthly_dd_limit_pct),
        monthly_risk_per_trade_pct=float(args.monthly_risk_per_trade_pct),
        risk_free_rate_annual=float(args.risk_free_rate_annual),
        trading_days_per_year=int(args.trading_days_per_year),
    )

    market_aware_refresh = not bool(args.disable_market_aware_refresh)

    candidates_source = "generated"
    if args.reuse_candidates_csv:
        candidates_source = "reused_csv"
        candidates_df = pd.read_csv(args.reuse_candidates_csv)
        symbols_for_prices = sorted(
            {
                str(s).strip().upper()
                for s in candidates_df.get("yf_symbol", pd.Series(dtype=object)).dropna().astype(str).tolist()
                if str(s).strip()
            }
        )
        if backtest_settings.benchmark_symbol not in symbols_for_prices:
            symbols_for_prices.append(backtest_settings.benchmark_symbol)

        prices_by_symbol, data_diag = fetch_prices(
            yf_symbols=symbols_for_prices,
            settings=backtest_settings,
            logger=logger,
            force_refresh=bool(args.force_refresh),
            market_aware_refresh=market_aware_refresh,
        )

        diagnostics = {
            "counts": {
                "symbols_requested": int(len(symbols_for_prices)),
                "symbols_excluding_benchmark": max(0, int(len(symbols_for_prices) - 1)),
                "downloaded_symbols": int(data_diag.downloaded_symbols),
                "cached_symbols": int(data_diag.cached_symbols),
                "skipped_symbols": int(len(data_diag.skipped)),
                "trades": 0,
                "candidates": int(len(candidates_df)),
            },
            "skipped_symbols": list(data_diag.skipped),
            "config": {
                "start_date": config.start_date,
                "end_date": config.end_date,
                "engine": config.engine,
                "warmup_bars": config.warmup_bars,
                "min_avg_dollar_volume_20d": float(backtest_settings.min_avg_dollar_volume_20d),
                "force_refresh": bool(args.force_refresh),
                "market_aware_refresh": bool(market_aware_refresh),
                "reused_candidates_csv": str(args.reuse_candidates_csv),
            },
        }
    else:
        result = run_backtest(
            symbols=symbols,
            settings=backtest_settings,
            config=config,
            logger=logger,
            force_refresh=bool(args.force_refresh),
            market_aware_refresh=market_aware_refresh,
        )
        candidates_df = result.candidates
        prices_by_symbol = result.prices
        diagnostics = dict(result.diagnostics)

    portfolio_result = simulate_portfolio(
        candidates=candidates_df,
        prices_by_symbol=prices_by_symbol,
        benchmark_symbol=backtest_settings.benchmark_symbol,
        start_date=resolved_start_date,
        end_date=resolved_end_date,
        config=portfolio_cfg,
    )

    trades_csv_path = write_trade_log(portfolio_result.executed_trades, out_dir="data/backtests")
    stats = summarize_trades(portfolio_result.executed_trades)

    portfolio_payload = {
        "assumptions": _portfolio_assumptions_dict(portfolio_cfg),
        "metrics": portfolio_result.metrics,
        "curve": {
            "dates": portfolio_result.equity_curve.get("date", pd.Series(dtype=object)).astype(str).tolist(),
            "equity": portfolio_result.equity_curve.get("equity", pd.Series(dtype=float)).astype(float).round(4).tolist(),
            "drawdown_pct": portfolio_result.equity_curve.get("drawdown_pct", pd.Series(dtype=float)).astype(float).round(4).tolist(),
        },
        "monthly_returns": portfolio_result.monthly_returns.to_dict(orient="records"),
    }

    counts = dict((diagnostics.get("counts") or {}))
    counts["portfolio_executed_trades"] = int(len(portfolio_result.executed_trades))
    counts["portfolio_rejected_entries"] = int(portfolio_result.metrics.get("rejected_entries", 0) or 0)
    counts["portfolio_months_halted"] = int(portfolio_result.metrics.get("months_halted", 0) or 0)
    diagnostics["counts"] = counts
    diagnostics["portfolio_execution"] = _build_diagnostics_summary(
        candidates=candidates_df,
        executed_trades=portfolio_result.executed_trades,
        fills_log=portfolio_result.fills_log,
    )

    run_id = str(args.run_id).strip() if args.run_id else datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    run_config = _build_run_config(
        args=args,
        symbols=symbols,
        benchmark_symbol=backtest_settings.benchmark_symbol,
        portfolio_cfg=portfolio_cfg,
        lookback_calendar_days=backtest_settings.lookback_calendar_days,
        start_date=resolved_start_date,
        end_date=resolved_end_date,
        years=args.years,
    )
    run_config["scenario"] = {
        "candidates_source": candidates_source,
        "reuse_candidates_csv": str(args.reuse_candidates_csv) if args.reuse_candidates_csv else None,
    }

    run_config_path = write_run_config_json(run_config, run_id=run_id, out_dir="docs/data/backtest_runs")
    symbols_path = write_symbols_json(symbols, run_id=run_id, out_dir="docs/data/backtest_runs")
    candidates_path = write_candidates_csv(candidates_df, run_id=run_id, out_dir="docs/data/backtest_runs")

    benchmark_payload = _compute_spy_benchmark_metrics(
        prices_by_symbol=prices_by_symbol,
        benchmark_symbol=backtest_settings.benchmark_symbol,
        start_date=resolved_start_date,
        end_date=resolved_end_date,
        strategy_total_return_pct=portfolio_result.metrics.get("total_return_pct"),
        strategy_cagr_pct=portfolio_result.metrics.get("cagr_pct"),
    )

    summary_payload = build_summary_payload(
        engine=args.engine,
        start_date=resolved_start_date,
        end_date=resolved_end_date,
        symbol_mode=args.symbol_mode,
        symbol_count=len(symbols),
        benchmark_symbol=backtest_settings.benchmark_symbol,
        stats=stats,
        diagnostics=diagnostics,
        trades_path=trades_csv_path,
        portfolio=portfolio_payload,
        benchmark=benchmark_payload,
        methodology=_build_methodology_meta(portfolio_cfg),
        run_id=run_id,
        run_config=run_config,
        symbols_path=str(symbols_path).replace("\\", "/"),
        run_config_path=str(run_config_path).replace("\\", "/"),
        candidates_path=str(candidates_path).replace("\\", "/"),
    )
    history_path = write_summary_history_json(summary_payload, run_id=run_id, out_dir="docs/data/backtest_runs")

    summary_payload = build_summary_payload(
        engine=args.engine,
        start_date=resolved_start_date,
        end_date=resolved_end_date,
        symbol_mode=args.symbol_mode,
        symbol_count=len(symbols),
        benchmark_symbol=backtest_settings.benchmark_symbol,
        stats=stats,
        diagnostics=diagnostics,
        trades_path=trades_csv_path,
        portfolio=portfolio_payload,
        benchmark=benchmark_payload,
        methodology=_build_methodology_meta(portfolio_cfg),
        run_id=run_id,
        run_config=run_config,
        symbols_path=str(symbols_path).replace("\\", "/"),
        run_config_path=str(run_config_path).replace("\\", "/"),
        summary_history_path=str(history_path).replace("\\", "/"),
        candidates_path=str(candidates_path).replace("\\", "/"),
    )
    write_summary_json(summary_payload, path="docs/data/backtest_summary.json")
    write_summary_json(summary_payload, path=str(history_path).replace("\\", "/"))
    runs_index_path = write_backtest_runs_index_json(out_dir="docs/data/backtest_runs")

    trade_log_csv = str(trades_csv_path).replace("\\", "/")
    symbols_json = str(symbols_path).replace("\\", "/")
    run_config_json = str(run_config_path).replace("\\", "/")
    run_summary_json = str(history_path).replace("\\", "/")
    candidates_csv = str(candidates_path).replace("\\", "/")

    runs_index_json = str(runs_index_path).replace("\\", "/")

    print(format_summary_table(summary_payload))
    print(f"Run Name: {run_config.get('run_name', '-')}")
    print(f"Run Description: {run_config.get('run_description', '-')}")
    print(f"Run ID: {run_id}")
    print(f"Trade log CSV: {trade_log_csv}")
    print(f"Symbols JSON: {symbols_json}")
    print(f"Run Config JSON: {run_config_json}")
    print(f"Run Summary JSON: {run_summary_json}")
    print(f"Candidates CSV: {candidates_csv}")
    print(f"Runs Index JSON: {runs_index_json}")
    print("Summary JSON: docs/data/backtest_summary.json")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
