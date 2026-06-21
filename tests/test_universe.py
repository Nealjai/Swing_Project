from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.screener.universe import load_universe, normalize_for_yfinance


class UniverseLoadingTests(unittest.TestCase):
    def test_normalize_for_yfinance_replaces_dots(self) -> None:
        self.assertEqual(normalize_for_yfinance("BRK.B"), "BRK-B")

    def test_load_universe_ignores_comments_blanks_invalid_and_dedupes(self) -> None:
        raw = """
# main universe
AAPL
MSFT

INVALID$SYM
BRK.B
BRK-B  # duplicate after yfinance normalization
TSLA
# trailing comment line
""".strip()

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "universe.txt"
            path.write_text(raw, encoding="utf-8")

            items = load_universe(str(path))

        symbols = [item.symbol for item in items]
        yf_symbols = [item.yf_symbol for item in items]

        self.assertEqual(symbols, ["AAPL", "MSFT", "BRK.B", "TSLA"])
        self.assertEqual(yf_symbols, ["AAPL", "MSFT", "BRK-B", "TSLA"])

    def test_load_universe_raises_for_missing_file(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_universe("does_not_exist_universe_file.txt")


if __name__ == "__main__":
    unittest.main()
