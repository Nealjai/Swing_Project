from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List


_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9.\-/]*$")


@dataclass(frozen=True)
class UniverseItem:
    symbol: str
    yf_symbol: str


def normalize_for_yfinance(symbol: str) -> str:
    return symbol.strip().upper().replace(".", "-")


def _strip_inline_comment(line: str) -> str:
    return line.split("#", 1)[0].strip()


def _is_valid_symbol(symbol: str) -> bool:
    return bool(_SYMBOL_PATTERN.fullmatch(symbol.strip().upper()))


def load_universe(path: str) -> List[UniverseItem]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Universe file not found: {path}")

    items: List[UniverseItem] = []
    seen_yf_symbols = set()

    for raw in file_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        symbol = _strip_inline_comment(line).upper()
        if not symbol or not _is_valid_symbol(symbol):
            continue

        yf_symbol = normalize_for_yfinance(symbol)
        if yf_symbol in seen_yf_symbols:
            continue

        seen_yf_symbols.add(yf_symbol)
        items.append(UniverseItem(symbol=symbol, yf_symbol=yf_symbol))

    return items
