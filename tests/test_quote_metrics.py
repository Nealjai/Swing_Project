from __future__ import annotations

import unittest

import pandas as pd

from src.screener.quote_metrics import compute_beta_1y_from_prices, summarize_quote_metrics_coverage


class QuoteMetricsTests(unittest.TestCase):
    def test_compute_beta_1y_from_prices_uses_adj_close_returns(self) -> None:
        idx = pd.date_range("2025-01-01", periods=8, freq="B")

        benchmark_adj = [100.0, 101.0, 102.0, 101.5, 103.0, 104.0, 105.0, 106.0]
        stock_adj = [50.0, 50.6, 51.2, 50.9, 51.8, 52.4, 53.0, 53.6]

        stock = pd.DataFrame({"Adj Close": stock_adj, "Close": [x * 1.01 for x in stock_adj]}, index=idx)
        benchmark = pd.DataFrame({"Adj Close": benchmark_adj, "Close": [x * 0.99 for x in benchmark_adj]}, index=idx)

        beta, obs = compute_beta_1y_from_prices(stock, benchmark, lookback_days=252, min_obs=4)

        self.assertIsNotNone(beta)
        self.assertGreater(obs, 0)

        stock_ret = pd.Series(stock_adj, index=idx).pct_change().dropna()
        bench_ret = pd.Series(benchmark_adj, index=idx).pct_change().dropna()
        expected = float(stock_ret.cov(bench_ret) / bench_ret.var(ddof=1))
        self.assertAlmostEqual(float(beta), expected, places=10)

    def test_compute_beta_1y_from_prices_returns_none_when_insufficient_observations(self) -> None:
        idx = pd.date_range("2025-01-01", periods=3, freq="B")
        stock = pd.DataFrame({"Adj Close": [10.0, 10.1, 10.2]}, index=idx)
        benchmark = pd.DataFrame({"Adj Close": [100.0, 100.1, 100.2]}, index=idx)

        beta, obs = compute_beta_1y_from_prices(stock, benchmark, lookback_days=252, min_obs=10)

        self.assertIsNone(beta)
        self.assertLess(obs, 10)

    def test_summarize_quote_metrics_coverage_counts(self) -> None:
        symbols = ["AAPL", "MSFT", "TSLA", "TSLA", " ", "spy"]
        metrics = {
            "AAPL": {"market_cap": 1_000_000.0, "beta_1y": 1.2},
            "MSFT": {"market_cap": None, "beta_1y": 0.9},
            "TSLA": {"market_cap": 900_000.0, "beta_1y": None},
            "SPY": {"market_cap": None, "beta_1y": None},
        }

        summary = summarize_quote_metrics_coverage(symbols, metrics)

        self.assertEqual(summary["attempted_count"], 4)
        self.assertEqual(summary["success_count"], 1)
        self.assertEqual(summary["missing_market_cap_count"], 1)
        self.assertEqual(summary["missing_beta_1y_count"], 1)
        self.assertEqual(summary["missing_both_count"], 1)
        self.assertAlmostEqual(summary["success_rate"], 0.25)


if __name__ == "__main__":
    unittest.main()
