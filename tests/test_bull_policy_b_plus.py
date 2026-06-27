from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from src.screener.engines.bull import bull_candidates
from src.screener.tracker import _compute_leadership_thresholds, _is_tracker_eligible, _new_tracker_record, _refresh_record


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
    def setUp(self) -> None:
        self.leadership_thresholds = {
            "strict": 0.90,
            "pullback": 0.85,
            "breakout": 0.88,
        }

    def test_tracker_rejects_watchlist_intent(self) -> None:
        candidate = {
            "engine": "playbook",
            "intent": "watchlist",
            "rank": 1,
            "leadership_score": 0.95,
            "actionability_score": 0.70,
            "risk": {"position_sizing": {"max_shares": 10}},
        }
        self.assertFalse(_is_tracker_eligible(candidate, leadership_thresholds=self.leadership_thresholds))

    def test_tracker_rejects_zero_max_shares(self) -> None:
        candidate = {
            "engine": "playbook",
            "intent": "trade",
            "rank": 1,
            "leadership_score": 0.95,
            "actionability_score": 0.70,
            "risk": {"position_sizing": {"max_shares": 0}},
        }
        self.assertFalse(_is_tracker_eligible(candidate, leadership_thresholds=self.leadership_thresholds))

    def test_tracker_accepts_trade_intent_on_strict_trophy_lightning_route(self) -> None:
        candidate = {
            "engine": "playbook",
            "intent": "trade",
            "rank": 1,
            "leadership_score": 0.95,
            "actionability_score": 0.70,
            "risk": {"position_sizing": {"max_shares": 10}},
        }
        self.assertTrue(_is_tracker_eligible(candidate, leadership_thresholds=self.leadership_thresholds))

    def test_tracker_accepts_trade_intent_on_relaxed_pullback_route(self) -> None:
        candidate = {
            "engine": "playbook",
            "playbook_id": "PULLBACK_ENTRY",
            "intent": "trade",
            "rank": 2,
            "leadership_score": 0.86,
            "actionability_score": 0.56,
            "risk": {"position_sizing": {"max_shares": 7}},
        }
        self.assertTrue(_is_tracker_eligible(candidate, leadership_thresholds=self.leadership_thresholds))

    def test_compute_leadership_thresholds_returns_quantiles(self) -> None:
        candidates = [
            {"leadership_score": 0.60},
            {"leadership_score": 0.70},
            {"leadership_score": 0.80},
            {"leadership_score": 0.90},
            {"leadership_score": 1.00},
        ]
        thresholds = _compute_leadership_thresholds(candidates)

        self.assertGreaterEqual(thresholds["strict"], thresholds["breakout"])
        self.assertGreaterEqual(thresholds["breakout"], thresholds["pullback"])
        self.assertGreaterEqual(thresholds["pullback"], 0.80)


class TrackerExecutionContractTests(unittest.TestCase):
    def test_new_record_derives_activation_from_entry_open_plus_2atr(self) -> None:
        candidate = {
            "symbol": "AAA",
            "engine": "playbook",
            "intent": "trade",
            "rank": 1,
            "score": 88.0,
            "risk": {
                "atr14": 1.0,
                "signal_close": 100.0,
            },
        }
        df = pd.DataFrame(
            {
                "Open": [100.0],
                "High": [101.0],
                "Low": [99.0],
                "Close": [100.5],
            },
            index=pd.to_datetime(["2026-01-02"]),
        )

        record = _new_tracker_record(
            candidate,
            current_date=date(2026, 1, 2),
            latest={"df": df, "current_close": 100.5},
        )

        self.assertEqual(record.get("entry_date_utc"), "2026-01-02")
        self.assertEqual(record.get("entry_price"), 100.0)
        self.assertEqual(record.get("activation_level"), 102.0)

    def test_refresh_activates_on_intraday_high_and_sets_hard_partial_exit(self) -> None:
        candidate = {
            "symbol": "AAA",
            "engine": "playbook",
            "intent": "trade",
            "rank": 1,
            "score": 88.0,
            "risk": {
                "atr14": 1.0,
                "signal_close": 100.0,
            },
        }
        df = pd.DataFrame(
            {
                "Open": [100.0, 101.0],
                "High": [103.0, 101.0],
                "Low": [99.0, 100.0],
                "Close": [102.0, 100.0],
            },
            index=pd.to_datetime(["2026-01-02", "2026-01-05"]),
        )

        record = _new_tracker_record(
            candidate,
            current_date=date(2026, 1, 2),
            latest={"df": df, "current_close": 102.0},
        )

        refreshed = _refresh_record(
            record,
            latest={
                "current_close": 100.0,
                "distance_to_sma20_pct": None,
                "rsi14": None,
                "volume_buzz_ratio": None,
                "df": df,
                "df_index": df.index,
            },
            current_date=date(2026, 1, 5),
        )

        self.assertTrue(bool(refreshed.get("activated")))
        self.assertEqual(refreshed.get("activation_date_utc"), "2026-01-02")
        self.assertEqual(refreshed.get("activation_price"), 102.0)
        self.assertTrue(bool(refreshed.get("partial_exit_done")))
        self.assertEqual(refreshed.get("partial_exit_fraction"), 0.5)
        self.assertEqual(refreshed.get("position_state"), "inactive")
        self.assertEqual(refreshed.get("exit_reason"), "trailing_stop_intraday")


if __name__ == "__main__":
    unittest.main()
