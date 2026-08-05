from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.screener.engines.playbook import select_playbook_candidates
from src.screener.export import export_outputs


class PlaybookSelectionTests(unittest.TestCase):
    def test_bear_regime_routes_breakout_to_watchlist(self) -> None:
        candidates = [
            {
                "engine": "bull",
                "symbol": "AAA",
                "close": 120.0,
                "avg_dollar_volume_20d": 120_000_000.0,
                "atr14": 3.0,
                "median_dollar_volume_20d": 121_000_000.0,
                "leadership_score": 0.82,
                "actionability_score": 0.80,
                "pattern_stage": "breakout",
                "breakout_state": "breakout",
            }
        ]

        selected, policy = select_playbook_candidates(
            candidates,
            regime_label="Bear",
            min_price=5.0,
            min_avg_dollar_volume_20d=20_000_000.0,
            max_atr_pct=0.20,
        )

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].get("playbook_id"), "BREAKOUT")
        self.assertEqual(selected[0].get("intent"), "watchlist")
        self.assertFalse(policy.get("trade_allowed"))
        self.assertEqual(policy.get("cash_reason"), "watchlist_only_no_regime_permitted_trade")

    def test_absolute_gate_can_block_all_candidates(self) -> None:
        candidates = [
            {
                "engine": "weak",
                "symbol": "BBB",
                "close": 4.0,
                "avg_dollar_volume_20d": 5_000_000.0,
                "atr14": 0.8,
                "median_dollar_volume_20d": 5_000_000.0,
                "leadership_score": 0.95,
                "actionability_score": 0.95,
                "playbook_id": "CAP_RECLAIM",
            }
        ]

        selected, policy = select_playbook_candidates(
            candidates,
            regime_label="Bull",
            min_price=5.0,
            min_avg_dollar_volume_20d=20_000_000.0,
            max_atr_pct=0.20,
        )

        self.assertEqual(selected, [])
        self.assertFalse(policy.get("trade_allowed"))
        self.assertEqual(policy.get("cash_reason"), "no_candidates_passed_absolute_gates")


class ExportPayloadTests(unittest.TestCase):
    def test_export_contains_trade_and_risk_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            json_path = str(Path(tmp) / "latest.json")
            csv_path = str(Path(tmp) / "latest.csv")

            export_outputs(
                settings_snapshot={
                    "benchmark_symbol": "SPY",
                    "min_price": 5.0,
                    "min_market_cap": 3_000_000_000.0,
                    "min_beta_1y": 1.0,
                    "min_volume": 500_000.0,
                    "min_avg_dollar_volume_20d": 20_000_000.0,
                    "min_avg_dollar_volume_20d_bull": 30_000_000.0,
                    "min_avg_dollar_volume_20d_choppy": 75_000_000.0,
                    "min_avg_dollar_volume_20d_bear": 100_000_000.0,
                    "min_atr_dollars": 0.50,
                    "atr_pct_tier_lt_20": 0.12,
                    "atr_pct_tier_20_to_100": 0.10,
                    "atr_pct_tier_gt_100": 0.08,
                    "sma_regime_length": 200,
                    "breakout_lookback": 20,
                    "rsi_length": 14,
                    "bb_length": 20,
                    "bb_std": 2.0,
                    "weak_rsi_threshold": 30.0,
                    "max_candidates": 50,
                    "max_atr_pct": 0.08,
                },
                benchmark={"symbol": "SPY", "close": 500.0, "sma200": 480.0, "above_sma200": True},
                candidates=[{"symbol": "AAA", "score": 88.0}],
                diagnostics={
                    "counts": {"ranked_candidates_count": 1, "run_duration_seconds": 12.345},
                    "run_timing": {
                        "started_at_utc": "2026-01-01T00:00:00+00:00",
                        "finished_at_utc": "2026-01-01T00:00:12+00:00",
                        "duration_seconds": 12.345,
                    },
                },
                regime="Bull",
                engine="playbook",
                universe_size=1200,
                json_path=json_path,
                csv_path=csv_path,
                trade_policy={
                    "trade_allowed": False,
                    "cash_reason": "no_candidates_passed_absolute_gates",
                    "qualified_trade_count": 0,
                },
                risk_policy={
                    "initial_capital": 10_000.0,
                    "max_positions": 6,
                },
            )

            payload = json.loads(Path(json_path).read_text(encoding="utf-8"))
            self.assertIn("trade_policy", payload)
            self.assertIn("risk_policy", payload)
            self.assertFalse(payload.get("trade_allowed"))
            self.assertEqual(payload.get("cash_reason"), "no_candidates_passed_absolute_gates")
            self.assertEqual(payload.get("qualified_trade_count"), 0)
            self.assertEqual(payload.get("diagnostics", {}).get("counts", {}).get("run_duration_seconds"), 12.345)
            self.assertEqual(payload.get("diagnostics", {}).get("run_timing", {}).get("duration_seconds"), 12.345)
            scanner_settings = payload.get("scanner_settings", {})
            self.assertEqual(scanner_settings.get("min_avg_dollar_volume_20d_bull"), 30_000_000.0)
            self.assertEqual(scanner_settings.get("min_avg_dollar_volume_20d_choppy"), 75_000_000.0)
            self.assertEqual(scanner_settings.get("min_avg_dollar_volume_20d_bear"), 100_000_000.0)
            self.assertEqual(scanner_settings.get("min_atr_dollars"), 0.50)
            self.assertEqual(scanner_settings.get("atr_pct_tier_lt_20"), 0.12)
            self.assertEqual(scanner_settings.get("atr_pct_tier_20_to_100"), 0.10)
            self.assertEqual(scanner_settings.get("atr_pct_tier_gt_100"), 0.08)


if __name__ == "__main__":
    unittest.main()
