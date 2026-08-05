from __future__ import annotations

import unittest

from src.screener.fundamentals import summarize_ticker_info_coverage


class TickerInfoCoverageTests(unittest.TestCase):
    def test_summarize_ticker_info_coverage_counts_success_empty_and_missing(self) -> None:
        symbols = ["AAPL", "MSFT", "TSLA", "TSLA", " ", "spy"]
        info_by_symbol = {
            "AAPL": {"marketCap": 100},
            "MSFT": {},
            "SPY": {"beta": 1.0},
        }

        summary = summarize_ticker_info_coverage(symbols, info_by_symbol)

        self.assertEqual(summary["attempted_count"], 4)
        self.assertEqual(summary["success_count"], 2)
        self.assertEqual(summary["empty_count"], 1)
        self.assertEqual(summary["missing_count"], 1)
        self.assertAlmostEqual(summary["success_rate"], 0.5)

        self.assertEqual(summary["successful_symbols"], ["AAPL", "SPY"])
        self.assertEqual(summary["empty_symbols"], ["MSFT"])
        self.assertEqual(summary["missing_symbols"], ["TSLA"])

    def test_summarize_ticker_info_coverage_handles_empty_input(self) -> None:
        summary = summarize_ticker_info_coverage([], None)

        self.assertEqual(summary["attempted_count"], 0)
        self.assertEqual(summary["success_count"], 0)
        self.assertEqual(summary["empty_count"], 0)
        self.assertEqual(summary["missing_count"], 0)
        self.assertEqual(summary["success_rate"], 0.0)
        self.assertEqual(summary["successful_symbols"], [])
        self.assertEqual(summary["empty_symbols"], [])
        self.assertEqual(summary["missing_symbols"], [])


if __name__ == "__main__":
    unittest.main()
