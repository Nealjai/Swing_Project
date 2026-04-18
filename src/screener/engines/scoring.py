from __future__ import annotations

import math
from statistics import median
from typing import Iterable


def to_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:  # noqa: BLE001
        return None


def clamp01(value: float) -> float:
    if value <= 0.0:
        return 0.0
    if value >= 1.0:
        return 1.0
    return float(value)


def sigmoid(value: float) -> float:
    # Numerically stable enough for scanner-scale z-scores.
    if value >= 35.0:
        return 1.0
    if value <= -35.0:
        return 0.0
    return 1.0 / (1.0 + math.exp(-value))


def robust_unit_score(
    value: float | None,
    population: Iterable[float | None],
    *,
    invert: bool = False,
    neutral: float = 0.5,
) -> float:
    """Map a raw feature to 0..1 with robust z-score + sigmoid.

    - Uses median and MAD (scaled by 1.4826) for outlier resistance.
    - Returns `neutral` for missing values or tiny populations.
    - `invert=True` means smaller raw values are better.
    """

    if value is None:
        return float(neutral)

    vals = [x for x in (to_float(v) for v in population) if x is not None]
    if len(vals) < 5:
        return float(neutral)

    med = median(vals)
    deviations = [abs(x - med) for x in vals]
    mad = median(deviations)

    if mad <= 1e-12:
        if abs(value - med) <= 1e-12:
            base = neutral
        else:
            base = 1.0 if value > med else 0.0
        return float(1.0 - base if invert else base)

    z = (value - med) / (1.4826 * mad)
    if invert:
        z = -z
    return float(clamp01(sigmoid(z)))
