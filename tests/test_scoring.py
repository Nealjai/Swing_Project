from __future__ import annotations

import math
import unittest

from src.screener.engines.scoring import robust_unit_score


class RobustUnitScoreTests(unittest.TestCase):
    def test_returns_neutral_for_missing_value(self) -> None:
        pop = [0.1, 0.2, 0.3, 0.4, 0.5]
        self.assertAlmostEqual(robust_unit_score(None, pop), 0.5, places=9)

    def test_returns_neutral_for_small_population(self) -> None:
        pop = [1.0, 2.0, 3.0, 4.0]
        self.assertAlmostEqual(robust_unit_score(2.0, pop), 0.5, places=9)

    def test_ignores_nan_inf_in_population(self) -> None:
        pop = [1.0, 2.0, math.nan, math.inf, 3.0, 4.0, 5.0]
        score = robust_unit_score(3.0, pop)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_mad_zero_non_equal_values_map_to_extremes(self) -> None:
        pop = [10.0, 10.0, 10.0, 10.0, 10.0]
        self.assertEqual(robust_unit_score(10.0, pop), 0.5)
        self.assertEqual(robust_unit_score(11.0, pop), 1.0)
        self.assertEqual(robust_unit_score(9.0, pop), 0.0)

    def test_invert_flips_direction(self) -> None:
        pop = [1.0, 2.0, 3.0, 4.0, 5.0]
        normal = robust_unit_score(5.0, pop)
        inverted = robust_unit_score(5.0, pop, invert=True)
        self.assertGreater(normal, 0.5)
        self.assertLess(inverted, 0.5)

    def test_output_bounded_to_unit_interval(self) -> None:
        pop = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        low = robust_unit_score(-1_000_000.0, pop)
        high = robust_unit_score(1_000_000.0, pop)
        self.assertGreaterEqual(low, 0.0)
        self.assertLessEqual(low, 1.0)
        self.assertGreaterEqual(high, 0.0)
        self.assertLessEqual(high, 1.0)


if __name__ == "__main__":
    unittest.main()
