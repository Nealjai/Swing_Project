from __future__ import annotations

import unittest

import pandas as pd

from src.screener.backtest.portfolio import PortfolioConfig, simulate_portfolio


class PortfolioExecutionContractTests(unittest.TestCase):
    def _price_frame(
        self,
        dates: list[str],
        open_px: list[float],
        high_px: list[float],
        low_px: list[float],
        close_px: list[float],
    ) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "Open": open_px,
                "High": high_px,
                "Low": low_px,
                "Close": close_px,
            },
            index=pd.to_datetime(dates),
        )

    def test_portfolio_ignores_legacy_tp_exit_branches(self) -> None:
        dates = ["2026-01-02", "2026-01-05"]
        prices_by_symbol = {
            "AAA": self._price_frame(
                dates=dates,
                open_px=[100.0, 104.0],
                high_px=[105.0, 104.5],
                low_px=[99.0, 101.0],
                close_px=[104.0, 103.0],
            ),
            "SPY": self._price_frame(
                dates=dates,
                open_px=[500.0, 501.0],
                high_px=[501.0, 502.0],
                low_px=[499.0, 500.0],
                close_px=[500.5, 501.5],
            ),
        }

        candidates = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "yf_symbol": "AAA",
                    "engine": "bull",
                    "entry_date": "2026-01-02",
                    "exit_date": "2026-01-05",
                    "entry_price": 100.0,
                    "exit_price": 103.0,
                    "exit_reason": "time_stop",
                    "sl_level": 90.0,
                    # Intentionally present to verify it no longer drives exits.
                    "tp_level": 101.0,
                    "signal_avg_dollar_volume_20d": 100_000_000.0,
                    "activation_date": None,
                    "activation_price": None,
                    "partial_exit_fraction": 0.0,
                }
            ]
        )

        result = simulate_portfolio(
            candidates=candidates,
            prices_by_symbol=prices_by_symbol,
            benchmark_symbol="SPY",
            start_date="2026-01-02",
            end_date="2026-01-05",
            config=PortfolioConfig(),
        )

        executed = result.executed_trades
        self.assertEqual(len(executed), 1)
        exit_reason = str(executed.iloc[0].get("exit_reason") or "")
        self.assertEqual(exit_reason, "time_stop_at_close")
        self.assertFalse(exit_reason.startswith("tp_"))

    def test_partial_exit_logs_activation_reason_without_take_profit_wording(self) -> None:
        dates = ["2026-01-02", "2026-01-05"]
        prices_by_symbol = {
            "BBB": self._price_frame(
                dates=dates,
                open_px=[100.0, 99.5],
                high_px=[102.0, 100.0],
                low_px=[98.0, 98.0],
                close_px=[101.0, 99.0],
            ),
            "SPY": self._price_frame(
                dates=dates,
                open_px=[500.0, 500.5],
                high_px=[501.0, 501.0],
                low_px=[499.0, 499.5],
                close_px=[500.2, 500.8],
            ),
        }

        candidates = pd.DataFrame(
            [
                {
                    "symbol": "BBB",
                    "yf_symbol": "BBB",
                    "engine": "bull",
                    "entry_date": "2026-01-02",
                    "exit_date": "2026-01-05",
                    "entry_price": 100.0,
                    "exit_price": 99.0,
                    "exit_reason": "time_stop",
                    "sl_level": 90.0,
                    "signal_avg_dollar_volume_20d": 120_000_000.0,
                    "activation_date": "2026-01-02",
                    "activation_price": 101.5,
                    "partial_exit_fraction": 0.5,
                }
            ]
        )

        result = simulate_portfolio(
            candidates=candidates,
            prices_by_symbol=prices_by_symbol,
            benchmark_symbol="SPY",
            start_date="2026-01-02",
            end_date="2026-01-05",
            config=PortfolioConfig(),
        )

        fills = result.fills_log.copy()
        reasons = set(fills.get("reason", pd.Series(dtype=str)).astype(str).tolist())
        self.assertIn("activation_partial_exit_half", reasons)
        self.assertNotIn("activation_half_take_profit", reasons)


if __name__ == "__main__":
    unittest.main()
