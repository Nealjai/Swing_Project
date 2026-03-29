from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class UniverseItem:
    symbol: str
    yf_symbol: str


def normalize_for_yfinance(symbol: str) -> str:
    return symbol.strip().upper().replace(".", "-")


def load_universe(path: str) -> List[UniverseItem]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Universe file not found: {path}")

    items: List[UniverseItem] = []
    seen = set()
    for raw in file_path.read_text(encoding="utf-8").splitlines():
        symbol = raw.strip().upper()
        if not symbol:
            continue
        yf_symbol = normalize_for_yfinance(symbol)
        key = (symbol, yf_symbol)
        if key in seen:
            continue
        seen.add(key)
        items.append(UniverseItem(symbol=symbol, yf_symbol=yf_symbol))

    return items
