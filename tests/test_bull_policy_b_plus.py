from __future__ import annotations

import unittest

from src.screener.engines.bull import bull_candidates
from src.screener.tracker import _is_tracker_eligible


def _build_row(symbol: str, close: list[float], spy_close: list[float]) -> dict:
    open_px = [c * 0.999 for c in close]
    high = [c * 1.01 for c in close]
    low = [c * 0.99 for c in close]
    volume = [1_500_000.0 for _ in close]

    return {
        "symbol": symbol,
        "yf_symbol": symbol,
        "close": close[-1],
        "volume": volume[-1],
        "market_cap": 10_000_000_000.0,
        "beta_1y": 1.2,
        "avg_dollar_volume_20d": 120_000_000.0,
        "history": {
            "open": open_px,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "spy_close": spy_close,
        },
    }


class PolicyBPlusBullEngineTests(unittest.TestCase):
    def test_bear_regime_marks_relative_leader_as_watchlist_when_absolute_return_is_negative(self) -> None:
        # Stock is a slower loser than SPY over 20d -> positive excess return,
        # but still negative absolute return.
        stock_close = [120.0 - (0.25 * i) for i in range(120)]
        spy_close = [120.0 - (0.55 * i) for i in range(120)]

        rows = [_build_row("TEST1", stock_close, spy_close)]

        out = bull_candidates(
            rows,
            min_price=1.0,
            min_market_cap=1.0,
            min_beta_1y=0.0,
            min_volume=1.0,
            min_avg_dollar_volume_20d=0.0,
            regime_label="Bear",
        )

        self.assertEqual(len(out), 1)
        c = out[0]
        self.assertEqual(c.get("engine"), "bull")
        self.assertEqual(c.get("regime_label"), "Bear")
        self.assertEqual(c.get("intent"), "watchlist")

        dm = c.get("debug_metrics", {})
        self.assertIsNotNone(dm.get("stock_return_20d"))
        self.assertIsNotNone(dm.get("excess_return_20d"))
        self.assertLess(float(dm.get("stock_return_20d")), 0.0)
        self.assertGreater(float(dm.get("excess_return_20d")), 0.0)

    def test_bull_regime_defaults_to_trade_intent(self) -> None:
        stock_close = [100.0 + (0.30 * i) for i in range(120)]
        spy_close = [100.0 + (0.10 * i) for i in range(120)]

        rows = [_build_row("TEST2", stock_close, spy_close)]

        out = bull_candidates(
            rows,
            min_price=1.0,
            min_market_cap=1.0,
            min_beta_1y=0.0,
            min_volume=1.0,
            min_avg_dollar_volume_20d=0.0,
            regime_label="Bull",
        )

        self.assertEqual(len(out), 1)
        c = out[0]
        self.assertEqual(c.get("intent"), "trade")
        self.assertEqual(c.get("regime_policy"), "Policy B+")


class PolicyBPlusTrackerTests(unittest.TestCase):
    def test_tracker_rejects_watchlist_intent(self) -> None:
        candidate = {
            "engine": "bull",
            "intent": "watchlist",
            "rank": 1,
            "leadership_score": 0.95,
            "actionability_score": 0.70,
        }
        self.assertFalse(_is_tracker_eligible(candidate))

    def test_tracker_accepts_trade_intent_if_other_rules_pass(self) -> None:
        candidate = {
            "engine": "bull",
            "intent": "trade",
            "rank": 1,
            "leadership_score": 0.95,
            "actionability_score": 0.70,
        }
        self.assertTrue(_is_tracker_eligible(candidate))


if __name__ == "__main__":
    unittest.main()
