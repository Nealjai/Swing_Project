from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Sequence

import json
import logging
import math


@dataclass(frozen=True)
class PatternResult:
    pattern_type: str
    pattern_quality_score: float
    pivot_price: float | None
    pivot_test_count: int
    pivot_quality_score: float
    base_low: float | None
    cwh_score: float
    vcp_score: float
    contraction_sequence_score: float
    is_candidate: bool


def _to_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:  # noqa: BLE001
        return None


def _sma(values: Sequence[float], length: int) -> List[float | None]:
    out: List[float | None] = [None] * len(values)
    if length <= 0 or len(values) < length:
        return out
    rolling_sum = 0.0
    for i, v in enumerate(values):
        rolling_sum += v
        if i >= length:
            rolling_sum -= values[i - length]
        if i >= length - 1:
            out[i] = rolling_sum / float(length)
    return out


def _stddev(values: Sequence[float], length: int) -> float | None:
    if length <= 1 or len(values) < length:
        return None
    tail = values[-length:]
    m = sum(tail) / float(length)
    var = sum((x - m) ** 2 for x in tail) / float(length)
    return math.sqrt(var)


def _returns(close: Sequence[float], lookback: int) -> float | None:
    if lookback <= 0 or len(close) <= lookback:
        return None
    old = close[-lookback - 1]
    new = close[-1]
    if old <= 0:
        return None
    return (new / old) - 1.0


@lru_cache(maxsize=1024)
def _load_daily_history_from_docs(yf_symbol: str) -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = {"open": [], "high": [], "low": [], "close": [], "volume": []}
    safe_symbol = str(yf_symbol or "").replace("/", "_")
    if not safe_symbol:
        return out

    file_path = Path("docs") / "data" / "daily" / f"{safe_symbol}.json"
    if not file_path.exists():
        return out

    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return out

    if not isinstance(payload, dict):
        return out

    def _pick(container: Dict, *names: str) -> List[float] | None:
        for n in names:
            arr = container.get(n)
            if isinstance(arr, list):
                vals = [_to_float(v) for v in arr]
                if all(v is not None for v in vals):
                    return [float(v) for v in vals if v is not None]
        return None

    open_arr = _pick(payload, "Open", "open")
    high_arr = _pick(payload, "High", "high")
    low_arr = _pick(payload, "Low", "low")
    close_arr = _pick(payload, "Close", "close", "Adj Close", "adj_close")
    volume_arr = _pick(payload, "Volume", "volume")

    if open_arr and high_arr and low_arr and close_arr and volume_arr:
        n = min(len(open_arr), len(high_arr), len(low_arr), len(close_arr), len(volume_arr))
        out["open"] = open_arr[-n:]
        out["high"] = high_arr[-n:]
        out["low"] = low_arr[-n:]
        out["close"] = close_arr[-n:]
        out["volume"] = volume_arr[-n:]

    return out


def _extract_history_series(row: Dict) -> Dict[str, List[float]]:
    """Accept multiple row shapes and normalize to ohlcv lists.

    Supported containers:
    - row['history'] with keys Open/High/Low/Close/Volume (or lowercase)
    - row['ohlcv'] with lowercase keys
    - row['chart'] with lowercase keys
    - docs/data/daily/{yf_symbol}.json fallback when row does not embed history
    """

    containers: List[Dict] = []
    for key in ("history", "ohlcv", "chart", "series"):
        c = row.get(key)
        if isinstance(c, dict):
            containers.append(c)

    out: Dict[str, List[float]] = {"open": [], "high": [], "low": [], "close": [], "volume": [], "spy_close": []}

    def _pick(container: Dict, *names: str) -> List[float] | None:
        for n in names:
            arr = container.get(n)
            if isinstance(arr, list):
                vals = [_to_float(v) for v in arr]
                if all(v is not None for v in vals):
                    return [float(v) for v in vals if v is not None]
        return None

    for c in containers:
        open_arr = _pick(c, "Open", "open")
        high_arr = _pick(c, "High", "high")
        low_arr = _pick(c, "Low", "low")
        close_arr = _pick(c, "Close", "close", "Adj Close", "adj_close")
        volume_arr = _pick(c, "Volume", "volume")
        spy_arr = _pick(c, "spy_close", "SPY", "spy", "benchmark_close")

        if open_arr and high_arr and low_arr and close_arr and volume_arr:
            n = min(len(open_arr), len(high_arr), len(low_arr), len(close_arr), len(volume_arr))
            out["open"] = open_arr[-n:]
            out["high"] = high_arr[-n:]
            out["low"] = low_arr[-n:]
            out["close"] = close_arr[-n:]
            out["volume"] = volume_arr[-n:]
            if spy_arr:
                out["spy_close"] = spy_arr[-n:]
            break

    if not out["close"]:
        yf_symbol = str(row.get("yf_symbol") or row.get("symbol") or "")
        daily = _load_daily_history_from_docs(yf_symbol)
        out["open"] = daily["open"]
        out["high"] = daily["high"]
        out["low"] = daily["low"]
        out["close"] = daily["close"]
        out["volume"] = daily["volume"]

    if out["close"] and not out["spy_close"]:
        spy_daily = _load_daily_history_from_docs("SPY")
        spy_close = spy_daily["close"]
        if spy_close:
            n = min(len(out["close"]), len(out["open"]), len(out["high"]), len(out["low"]), len(out["volume"]), len(spy_close))
            out["open"] = out["open"][-n:]
            out["high"] = out["high"][-n:]
            out["low"] = out["low"][-n:]
            out["close"] = out["close"][-n:]
            out["volume"] = out["volume"][-n:]
            out["spy_close"] = spy_close[-n:]

    return out


def _compute_rs_block(close: Sequence[float], spy_close: Sequence[float], row: Dict) -> Dict[str, object]:
    # Fallback to precomputed row metrics if history is unavailable.
    rs_return_20d = _to_float(row.get("rs_return_20d"))
    rs_return_60d = _to_float(row.get("rs_return_60d"))
    rs_return_90d = _to_float(row.get("rs_return_90d"))
    rs_trending_up = bool(row.get("rs_trending_up", False))

    rs_line: List[float] = []
    if close and spy_close and len(close) == len(spy_close):
        rs_line = [(c / s) * 100.0 for c, s in zip(close, spy_close) if s > 0]
        if len(rs_line) >= 60:
            stock_20 = _returns(close, 20)
            stock_60 = _returns(close, 60)
            stock_90 = _returns(close, 90)
            spy_20 = _returns(spy_close, 20)
            spy_60 = _returns(spy_close, 60)
            spy_90 = _returns(spy_close, 90)

            if stock_20 is not None and spy_20 not in (None, 0.0):
                rs_return_20d = (stock_20 / float(spy_20)) - 1.0
            if stock_60 is not None and spy_60 not in (None, 0.0):
                rs_return_60d = (stock_60 / float(spy_60)) - 1.0
            if stock_90 is not None and spy_90 not in (None, 0.0):
                rs_return_90d = (stock_90 / float(spy_90)) - 1.0

            rs_line_sma_short = _sma(rs_line, 10)[-1]
            rs_line_sma_long = _sma(rs_line, 50)[-1]
            rs_trending_up = bool(
                rs_line_sma_short is not None
                and rs_line_sma_long is not None
                and rs_line_sma_short > rs_line_sma_long
            )

    rs_score = 0
    if rs_return_20d is not None and rs_return_20d > 0:
        rs_score += 1
    if rs_return_60d is not None and rs_return_60d > 0:
        rs_score += 1
    if rs_return_90d is not None and rs_return_90d > 0:
        rs_score += 1
    if rs_trending_up:
        rs_score += 2

    rs_pass = bool(
        (rs_return_20d is not None and rs_return_20d > 0)
        and (rs_return_60d is not None and rs_return_60d > 0)
        and rs_trending_up
    )

    return {
        "rs_line": rs_line,
        "rs_return_20d": rs_return_20d,
        "rs_return_60d": rs_return_60d,
        "rs_return_90d": rs_return_90d,
        "rs_trending_up": rs_trending_up,
        "rs_score": float(rs_score),
        "rs_pass": rs_pass,
    }


def _find_swing_highs(high: Sequence[float], span: int = 2) -> List[int]:
    idxs: List[int] = []
    if len(high) < (2 * span) + 1:
        return idxs
    for i in range(span, len(high) - span):
        left = high[i - span : i]
        right = high[i + 1 : i + span + 1]
        if all(high[i] >= x for x in left) and all(high[i] >= x for x in right):
            idxs.append(i)
    return idxs


def _find_swing_lows(low: Sequence[float], span: int = 2) -> List[int]:
    idxs: List[int] = []
    if len(low) < (2 * span) + 1:
        return idxs
    for i in range(span, len(low) - span):
        left = low[i - span : i]
        right = low[i + 1 : i + span + 1]
        if all(low[i] <= x for x in left) and all(low[i] <= x for x in right):
            idxs.append(i)
    return idxs


def _detect_cwh(high: Sequence[float], low: Sequence[float], close: Sequence[float], sma200: float | None) -> PatternResult:
    if len(close) < 80:
        return PatternResult("none", 0.0, None, 0, 0.0, None, 0.0, 0.0, 0.0, False)

    prior_uptrend_exists = bool(sma200 is not None and close[-1] > sma200)
    if not prior_uptrend_exists:
        return PatternResult("none", 0.0, None, 0, 0.0, None, 0.0, 0.0, 0.0, False)

    base_lookback = min(120, len(close) - 1)
    base_start = len(close) - base_lookback
    base_high = high[base_start:]
    base_low = low[base_start:]

    left_peak_rel = max(range(len(base_high)), key=lambda i: base_high[i])
    left_peak_idx = base_start + left_peak_rel
    left_peak = high[left_peak_idx]

    if left_peak_idx >= len(close) - 20:
        return PatternResult("none", 0.0, None, 0, 0.0, min(base_low), 0.0, 0.0, 0.0, False)

    bottom_idx = min(range(left_peak_idx + 1, len(close) - 10), key=lambda i: low[i])
    cup_bottom = low[bottom_idx]

    right_peak_idx = max(range(bottom_idx + 1, len(close) - 5), key=lambda i: high[i])
    right_peak = high[right_peak_idx]

    cup_depth_pct = (left_peak - cup_bottom) / left_peak if left_peak > 0 else 0.0
    cup_duration_bars = max(1, right_peak_idx - left_peak_idx)
    right_recovery_pct = right_peak / left_peak if left_peak > 0 else 0.0

    bottom_band = cup_bottom * 1.03
    bottom_zone_width = sum(1 for x in low[left_peak_idx:right_peak_idx + 1] if x <= bottom_band)
    is_rounded_cup = bottom_zone_width >= max(3, cup_duration_bars // 12)
    cup_depth_in_range = 0.10 <= cup_depth_pct <= 0.50

    handle_window = close[max(right_peak_idx, len(close) - 25) :]
    handle_high = max(handle_window) if handle_window else right_peak
    handle_low = min(handle_window) if handle_window else right_peak
    handle_depth_pct = (handle_high - handle_low) / handle_high if handle_high > 0 else 0.0
    handle_duration_bars = max(1, len(handle_window))
    cup_midpoint = cup_bottom + 0.5 * (left_peak - cup_bottom)

    handle_exists = len(handle_window) >= 5
    is_handle_high_enough = handle_low >= (cup_midpoint * 0.97)
    is_handle_smaller = (handle_depth_pct < cup_depth_pct) and (handle_duration_bars < cup_duration_bars)

    is_cwh_candidate = bool(
        prior_uptrend_exists
        and (is_rounded_cup or cup_depth_in_range)
        and right_recovery_pct >= 0.85
        and handle_exists
        and is_handle_high_enough
        and is_handle_smaller
    )

    cwh_score = 0.0
    if prior_uptrend_exists:
        cwh_score += 1.0
    if is_rounded_cup:
        cwh_score += 1.5
    if right_recovery_pct > 0.90:
        cwh_score += 1.0
    if is_handle_high_enough:
        cwh_score += 1.0
    if is_handle_smaller:
        cwh_score += 1.0
    if cup_depth_in_range:
        cwh_score += 1.0

    pivot_price = handle_high if handle_exists else right_peak

    return PatternResult(
        pattern_type="cwh" if is_cwh_candidate else "none",
        pattern_quality_score=float(cwh_score),
        pivot_price=float(pivot_price) if pivot_price > 0 else None,
        pivot_test_count=0,
        pivot_quality_score=0.0,
        base_low=float(min(base_low)) if base_low else None,
        cwh_score=float(cwh_score),
        vcp_score=0.0,
        contraction_sequence_score=0.0,
        is_candidate=is_cwh_candidate,
    )


def _compute_atr(high: Sequence[float], low: Sequence[float], close: Sequence[float], length: int) -> float | None:
    if len(close) <= length:
        return None
    tr: List[float] = []
    for i in range(1, len(close)):
        tr.append(max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1])))
    if len(tr) < length:
        return None
    return sum(tr[-length:]) / float(length)


def _detect_vcp(high: Sequence[float], low: Sequence[float], close: Sequence[float], volume: Sequence[float], sma200: float | None) -> PatternResult:
    if len(close) < 70:
        return PatternResult("none", 0.0, None, 0, 0.0, None, 0.0, 0.0, 0.0, False)

    prior_uptrend_exists = bool(sma200 is not None and close[-1] > sma200)
    if not prior_uptrend_exists:
        return PatternResult("none", 0.0, None, 0, 0.0, None, 0.0, 0.0, 0.0, False)

    base_lookback = min(100, len(close) - 1)
    start = len(close) - base_lookback

    sh = [i for i in _find_swing_highs(high[start:], span=2)]
    sl = [i for i in _find_swing_lows(low[start:], span=2)]
    swing_highs = [start + i for i in sh]
    swing_lows = [start + i for i in sl]

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return PatternResult("none", 0.0, None, 0, 0.0, float(min(low[start:])), 0.0, 0.0, 0.0, False)

    contractions: List[float] = []
    contraction_indices: List[tuple[int, int]] = []
    for hi_idx in swing_highs:
        possible_lows = [li for li in swing_lows if li > hi_idx]
        if not possible_lows:
            continue
        lo_idx = possible_lows[0]
        hi = high[hi_idx]
        lo = low[lo_idx]
        if hi <= 0:
            continue
        depth = (hi - lo) / hi
        if depth <= 0:
            continue
        contractions.append(depth)
        contraction_indices.append((hi_idx, lo_idx))
        if len(contractions) >= 4:
            break

    if len(contractions) < 2:
        return PatternResult("none", 0.0, None, 0, 0.0, float(min(low[start:])), 0.0, 0.0, 0.0, False)

    contraction_sequence_score = 0.0
    for i in range(1, len(contractions)):
        if contractions[i] < contractions[i - 1] * 1.08:  # allow mild noise
            contraction_sequence_score += 1.0

    depth_is_tightening = contraction_sequence_score >= max(1.0, len(contractions) - 1.5)

    ret_1d = [0.0]
    for i in range(1, len(close)):
        prev = close[i - 1]
        ret_1d.append(((close[i] / prev) - 1.0) if prev > 0 else 0.0)
    stddev_return_10d = _stddev(ret_1d, 10)
    stddev_return_30d = _stddev(ret_1d, 30)
    stddev_contraction_ratio = (
        (stddev_return_10d / stddev_return_30d)
        if stddev_return_10d is not None and stddev_return_30d not in (None, 0.0)
        else None
    )

    atr10 = _compute_atr(high, low, close, 10)
    atr50 = _compute_atr(high, low, close, 50)
    atr_contraction_ratio = (atr10 / atr50) if atr10 is not None and atr50 not in (None, 0.0) else None

    volatility_is_tightening = bool(
        (stddev_contraction_ratio is not None and stddev_contraction_ratio < 0.85)
        or (atr_contraction_ratio is not None and atr_contraction_ratio < 0.85)
    )

    last_hi_idx, last_lo_idx = contraction_indices[-1]
    avg_volume_base = sum(volume[start:]) / float(max(1, len(volume[start:])))
    final_contraction_volume = sum(volume[last_hi_idx : last_lo_idx + 1]) / float(max(1, last_lo_idx - last_hi_idx + 1))
    final_contraction_volume_low = final_contraction_volume <= (avg_volume_base * 1.05)

    pivot_price = max(high[last_hi_idx:]) if last_hi_idx < len(high) else None

    is_vcp_candidate = bool(
        prior_uptrend_exists and depth_is_tightening and volatility_is_tightening and final_contraction_volume_low
    )

    vcp_score = 0.0
    if prior_uptrend_exists:
        vcp_score += 1.0
    vcp_score += min(2.0, contraction_sequence_score)
    if volatility_is_tightening:
        vcp_score += 2.0
    if final_contraction_volume_low:
        vcp_score += 1.5
    if len(contractions) in (2, 3, 4):
        vcp_score += 1.0

    return PatternResult(
        pattern_type="vcp" if is_vcp_candidate else "none",
        pattern_quality_score=float(vcp_score),
        pivot_price=float(pivot_price) if pivot_price is not None else None,
        pivot_test_count=0,
        pivot_quality_score=0.0,
        base_low=float(min(low[start:])),
        cwh_score=0.0,
        vcp_score=float(vcp_score),
        contraction_sequence_score=float(contraction_sequence_score),
        is_candidate=is_vcp_candidate,
    )


def _pivot_analysis(high: Sequence[float], close: Sequence[float], pivot_hint: float | None) -> Dict[str, float | int | None]:
    if not high or not close:
        return {"pivot_price": pivot_hint, "pivot_test_count": 0, "pivot_distance_pct": None, "pivot_quality_score": 0.0}

    swing_highs_idx = _find_swing_highs(high, span=2)
    swing_highs = [high[i] for i in swing_highs_idx] if swing_highs_idx else []

    if swing_highs:
        max_high = max(swing_highs)
        tol = max_high * 0.01
        resistance_zone = [h for h in swing_highs if abs(h - max_high) <= tol]
        pivot_price = max(resistance_zone) if resistance_zone else max_high
        pivot_test_count = len(resistance_zone)
    else:
        pivot_price = pivot_hint if pivot_hint is not None else max(high[-20:])
        pivot_test_count = 1

    last_close = close[-1]
    pivot_distance_pct = ((pivot_price - last_close) / pivot_price) if pivot_price and pivot_price > 0 else None

    pivot_quality_score = 0.0
    if pivot_test_count >= 3:
        pivot_quality_score += 2.0
    elif pivot_test_count == 2:
        pivot_quality_score += 1.0

    if pivot_distance_pct is not None and 0.0 <= pivot_distance_pct <= 0.02:
        pivot_quality_score += 1.0

    return {
        "pivot_price": float(pivot_price) if pivot_price is not None else None,
        "pivot_test_count": int(pivot_test_count),
        "pivot_distance_pct": float(pivot_distance_pct) if pivot_distance_pct is not None else None,
        "pivot_quality_score": float(pivot_quality_score),
    }


def _volume_quality(close: Sequence[float], volume: Sequence[float], breakout_flag: bool, breakout_volume: float | None) -> Dict[str, float | bool | None]:
    if len(volume) < 50 or len(close) < 20:
        return {
            "volume_dryup_ratio": None,
            "up_down_volume_ratio": None,
            "breakout_volume_ratio": None,
            "pocket_pivot_flag": False,
            "volume_quality_score": 0.0,
        }

    sma10 = sum(volume[-10:]) / 10.0
    sma50 = sum(volume[-50:]) / 50.0
    volume_dryup_ratio = (sma10 / sma50) if sma50 > 0 else None

    up_vols = [volume[i] for i in range(len(close) - 20, len(close)) if i > 0 and close[i] > close[i - 1]]
    down_vols = [volume[i] for i in range(len(close) - 20, len(close)) if i > 0 and close[i] <= close[i - 1]]
    avg_up = (sum(up_vols) / len(up_vols)) if up_vols else None
    avg_down = (sum(down_vols) / len(down_vols)) if down_vols else None
    up_down_volume_ratio = (avg_up / avg_down) if avg_up is not None and avg_down not in (None, 0.0) else None

    sma20 = sum(volume[-20:]) / 20.0
    breakout_volume_ratio = (breakout_volume / sma20) if breakout_volume is not None and sma20 > 0 else None

    pocket_pivot_flag = bool(len(volume) >= 11 and close[-1] > close[-2] and volume[-1] > max(volume[-11:-1]))

    volume_quality_score = 0.0
    if volume_dryup_ratio is not None and volume_dryup_ratio < 0.6:
        volume_quality_score += 2.0
    if up_down_volume_ratio is not None and up_down_volume_ratio > 1.5:
        volume_quality_score += 1.0
    if breakout_flag and breakout_volume_ratio is not None and breakout_volume_ratio > 2.0:
        volume_quality_score += 3.0

    return {
        "volume_dryup_ratio": float(volume_dryup_ratio) if volume_dryup_ratio is not None else None,
        "up_down_volume_ratio": float(up_down_volume_ratio) if up_down_volume_ratio is not None else None,
        "breakout_volume_ratio": float(breakout_volume_ratio) if breakout_volume_ratio is not None else None,
        "pocket_pivot_flag": pocket_pivot_flag,
        "volume_quality_score": float(volume_quality_score),
    }


def _base_depth_score(high: Sequence[float], base_low: float | None) -> Dict[str, float | int | None]:
    if not high or base_low is None:
        return {"high_52w": None, "base_depth_pct": None, "base_depth_score": 0.0}

    lookback = min(252, len(high))
    high_52w = max(high[-lookback:])
    base_depth_pct = ((high_52w - base_low) / high_52w) if high_52w > 0 else None

    score = 0.0
    if base_depth_pct is not None:
        if 0.15 < base_depth_pct < 0.35:
            score = 2.0
        elif 0.10 < base_depth_pct < 0.50:
            score = 1.0
        else:
            score = -1.0

    return {
        "high_52w": float(high_52w),
        "base_depth_pct": float(base_depth_pct) if base_depth_pct is not None else None,
        "base_depth_score": float(score),
    }


def _breakout_state(close: Sequence[float], high: Sequence[float], low: Sequence[float], volume: Sequence[float], pivot_price: float | None) -> Dict[str, object]:
    if not close or pivot_price is None or pivot_price <= 0:
        return {
            "breakout_flag": False,
            "breakout_strength_pct": None,
            "close_location_in_range": None,
            "breakout_state": "pre_breakout",
            "days_since_breakout": None,
            "breakout_volume": None,
        }

    breakout_indices = [i for i, c in enumerate(close) if c > pivot_price]
    breakout_flag = len(breakout_indices) > 0
    last_close = close[-1]
    breakout_strength_pct = (last_close - pivot_price) / pivot_price

    day_range = high[-1] - low[-1]
    close_location_in_range = ((last_close - low[-1]) / day_range) if day_range > 0 else None

    days_since_breakout = None
    breakout_volume = None
    if breakout_flag:
        last_breakout_idx = breakout_indices[-1]
        days_since_breakout = len(close) - 1 - last_breakout_idx
        breakout_volume = volume[last_breakout_idx] if last_breakout_idx < len(volume) else None

    if breakout_flag and days_since_breakout is not None and days_since_breakout <= 3:
        state = "breakout"
    elif breakout_flag and days_since_breakout is not None and days_since_breakout > 3:
        state = "post_breakout_watch"
    else:
        state = "pre_breakout"

    return {
        "breakout_flag": breakout_flag,
        "breakout_strength_pct": float(breakout_strength_pct),
        "close_location_in_range": float(close_location_in_range) if close_location_in_range is not None else None,
        "breakout_state": state,
        "days_since_breakout": int(days_since_breakout) if days_since_breakout is not None else None,
        "breakout_volume": float(breakout_volume) if breakout_volume is not None else None,
    }


def _is_rebound_candle(open_px: Sequence[float], high: Sequence[float], low: Sequence[float], close: Sequence[float], sma20: float) -> bool:
    if len(close) < 2:
        return False

    # hammer-like candle near support
    body = abs(close[-1] - open_px[-1])
    lower_wick = min(close[-1], open_px[-1]) - low[-1]
    near_support = abs((close[-1] - sma20) / sma20) <= 0.02 if sma20 > 0 else False
    hammer = lower_wick > (body * 1.5) and near_support

    # bullish engulfing-style proxy
    prev_bear = close[-2] < open_px[-2]
    curr_bull = close[-1] > open_px[-1]
    engulf = curr_bull and prev_bear and close[-1] > open_px[-2] and open_px[-1] < close[-2]

    return bool(hammer or engulf)


def _pullback_engine(
    breakout_state: str,
    open_px: Sequence[float],
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    volume: Sequence[float],
) -> Dict[str, object]:
    pullback_entry_state = "none"
    entry_triangle_flag = False
    entry_triangle_price = None
    entry_triangle_date = None

    if breakout_state != "post_breakout_watch" or len(close) < 20:
        return {
            "sma20": None,
            "distance_to_sma20_pct": None,
            "pullback_volume_ratio": None,
            "support_rebound_flag": False,
            "pullback_entry_state": pullback_entry_state,
            "entry_triangle_flag": entry_triangle_flag,
            "entry_triangle_price": entry_triangle_price,
            "entry_triangle_date": entry_triangle_date,
        }

    sma20 = sum(close[-20:]) / 20.0
    distance_to_sma20_pct = ((close[-1] - sma20) / sma20) if sma20 > 0 else None

    sma3_vol = sum(volume[-3:]) / 3.0 if len(volume) >= 3 else None
    sma20_vol = sum(volume[-20:]) / 20.0 if len(volume) >= 20 else None
    pullback_volume_ratio = (sma3_vol / sma20_vol) if sma3_vol is not None and sma20_vol not in (None, 0.0) else None

    is_near_support = bool(distance_to_sma20_pct is not None and -0.02 <= distance_to_sma20_pct <= 0.02)
    is_volume_quiet = bool(pullback_volume_ratio is not None and pullback_volume_ratio < 1.0)

    support_rebound_flag = _is_rebound_candle(open_px, high, low, close, sma20)

    if is_near_support and is_volume_quiet:
        pullback_entry_state = "post-breakout-watch"

    if pullback_entry_state == "post-breakout-watch" and support_rebound_flag:
        pullback_entry_state = "pullback-entry-ready"
        entry_triangle_flag = True
        entry_triangle_price = float(low[-1])
        entry_triangle_date = int(len(close) - 1)

    return {
        "sma20": float(sma20),
        "distance_to_sma20_pct": float(distance_to_sma20_pct) if distance_to_sma20_pct is not None else None,
        "pullback_volume_ratio": float(pullback_volume_ratio) if pullback_volume_ratio is not None else None,
        "support_rebound_flag": support_rebound_flag,
        "pullback_entry_state": pullback_entry_state,
        "entry_triangle_flag": entry_triangle_flag,
        "entry_triangle_price": entry_triangle_price,
        "entry_triangle_date": entry_triangle_date,
    }


def _stage_sort_rank(pattern_stage: str) -> int:
    order = {
        "pullback-entry-ready": 0,
        "post-breakout-watch": 1,
        "breakout": 2,
        "near-pivot": 3,
        "early-stage": 4,
    }
    return order.get(pattern_stage, 99)


def bull_candidates(
    rows: List[Dict],
    min_price: float,
    min_market_cap: float,
    min_beta_1y: float,
    min_volume: float,
) -> List[Dict]:
    candidates: List[Dict] = []
    logger = logging.getLogger("screener")

    stats = {
        "total_rows": 0,
        "reject_missing_snapshot_fields": 0,
        "reject_static_thresholds": 0,
        "reject_missing_history": 0,
        "reject_short_history": 0,
        "reject_rs": 0,
        "prior_uptrend_pass": 0,
        "prior_uptrend_fail": 0,
        "cwh_candidate_count": 0,
        "vcp_candidate_count": 0,
        "reject_pattern": 0,
        "accepted": 0,
    }

    for row in rows:
        stats["total_rows"] += 1
        close_latest = _to_float(row.get("close"))
        volume_latest = _to_float(row.get("volume"))
        market_cap = _to_float(row.get("market_cap"))
        beta_1y = _to_float(row.get("beta_1y"))

        if close_latest is None or volume_latest is None or market_cap is None or beta_1y is None:
            stats["reject_missing_snapshot_fields"] += 1
            continue
        if close_latest <= min_price or market_cap <= min_market_cap or beta_1y <= min_beta_1y or volume_latest < min_volume:
            stats["reject_static_thresholds"] += 1
            continue

        hist = _extract_history_series(row)
        open_px = hist["open"]
        high = hist["high"]
        low = hist["low"]
        close = hist["close"]
        volume = hist["volume"]
        spy_close = hist["spy_close"]

        if not close:
            stats["reject_missing_history"] += 1
            continue
        if len(close) < 70:
            # Scanner requires sufficient OHLCV history for CWH/VCP approximation.
            stats["reject_short_history"] += 1
            continue

        # Keep SMA200 on the same price basis as pattern detection (history close series).
        sma200 = (sum(close[-200:]) / 200.0) if len(close) >= 200 else _to_float(row.get("sma200"))

        prior_uptrend_exists = bool(sma200 is not None and close[-1] > sma200)
        if prior_uptrend_exists:
            stats["prior_uptrend_pass"] += 1
        else:
            stats["prior_uptrend_fail"] += 1

        rs = _compute_rs_block(close, spy_close, row)
        if not rs["rs_pass"]:
            stats["reject_rs"] += 1
            continue

        cwh = _detect_cwh(high, low, close, sma200)
        vcp = _detect_vcp(high, low, close, volume, sma200)

        if cwh.is_candidate:
            stats["cwh_candidate_count"] += 1
        if vcp.is_candidate:
            stats["vcp_candidate_count"] += 1

        if cwh.is_candidate and vcp.is_candidate:
            chosen = cwh if cwh.pattern_quality_score >= vcp.pattern_quality_score else vcp
        elif cwh.is_candidate:
            chosen = cwh
        elif vcp.is_candidate:
            chosen = vcp
        else:
            stats["reject_pattern"] += 1
            continue

        pivot = _pivot_analysis(high, close, chosen.pivot_price)
        breakout = _breakout_state(close, high, low, volume, _to_float(pivot.get("pivot_price")))
        volume_block = _volume_quality(close, volume, bool(breakout["breakout_flag"]), _to_float(breakout.get("breakout_volume")))
        base_depth = _base_depth_score(high, chosen.base_low)
        pullback = _pullback_engine(
            breakout_state=str(breakout["breakout_state"]),
            open_px=open_px,
            high=high,
            low=low,
            close=close,
            volume=volume,
        )

        pivot_distance_pct = _to_float(pivot.get("pivot_distance_pct"))
        breakout_state = str(breakout["breakout_state"])
        pullback_entry_state = str(pullback["pullback_entry_state"])

        if pullback_entry_state == "pullback-entry-ready":
            pattern_stage = "pullback-entry-ready"
        elif pullback_entry_state == "post-breakout-watch":
            pattern_stage = "post-breakout-watch"
        elif breakout_state == "breakout":
            pattern_stage = "breakout"
        elif pivot_distance_pct is not None and pivot_distance_pct < 0.02:
            pattern_stage = "near-pivot"
        else:
            pattern_stage = "early-stage"

        pattern_quality_score = (
            float(chosen.pattern_quality_score)
            + float(volume_block["volume_quality_score"])
            + float(base_depth["base_depth_score"])
            + float(pivot["pivot_quality_score"])
        )

        stage_bonus = float(max(0, 5 - _stage_sort_rank(pattern_stage)) * 10)
        score = stage_bonus + (pattern_quality_score * 5.0) + float(rs["rs_score"] * 3.0)

        reasons = [
            f"RS passed: rs20={rs['rs_return_20d']}, rs60={rs['rs_return_60d']}, rs_trending_up={rs['rs_trending_up']}",
            f"Pattern detected: {chosen.pattern_type.upper()} quality={chosen.pattern_quality_score:.2f}",
            f"Stage: {pattern_stage}, breakout_state={breakout_state}, pullback_state={pullback_entry_state}",
            f"Pivot: pivot_price={pivot.get('pivot_price')}, distance={pivot.get('pivot_distance_pct')}",
        ]

        stats["accepted"] += 1

        candidates.append(
            {
                **row,
                "engine": "bull",
                "score": float(score),
                "pattern_type": chosen.pattern_type,
                "pattern_quality_score": float(pattern_quality_score),
                "pattern_stage": pattern_stage,
                "rs_score": float(rs["rs_score"]),
                "contraction_score": float(chosen.contraction_sequence_score),
                "volume_quality_score": float(volume_block["volume_quality_score"]),
                "base_depth_score": float(base_depth["base_depth_score"]),
                "pivot_quality_score": float(pivot["pivot_quality_score"]),
                "breakout_state": breakout_state,
                "pivot_price": pivot.get("pivot_price"),
                "pivot_distance_pct": pivot.get("pivot_distance_pct"),
                "breakout_strength_pct": breakout.get("breakout_strength_pct"),
                "pullback_entry_state": pullback_entry_state,
                "entry_triangle_flag": pullback.get("entry_triangle_flag"),
                "entry_triangle_price": pullback.get("entry_triangle_price"),
                "entry_triangle_date": pullback.get("entry_triangle_date"),
                "score_breakdown": {
                    "stage_bonus": stage_bonus,
                    "pattern_quality_score": float(pattern_quality_score),
                    "rs_score": float(rs["rs_score"]),
                    "cwh_score": float(chosen.cwh_score),
                    "vcp_score": float(chosen.vcp_score),
                    "contraction_sequence_score": float(chosen.contraction_sequence_score),
                    "volume_quality_score": float(volume_block["volume_quality_score"]),
                    "base_depth_score": float(base_depth["base_depth_score"]),
                    "pivot_quality_score": float(pivot["pivot_quality_score"]),
                },
                "debug_metrics": {
                    "rs_return_20d": rs["rs_return_20d"],
                    "rs_return_60d": rs["rs_return_60d"],
                    "rs_return_90d": rs["rs_return_90d"],
                    "rs_trending_up": rs["rs_trending_up"],
                    "volume_dryup_ratio": volume_block["volume_dryup_ratio"],
                    "up_down_volume_ratio": volume_block["up_down_volume_ratio"],
                    "breakout_volume_ratio": volume_block["breakout_volume_ratio"],
                    "pocket_pivot_flag": volume_block["pocket_pivot_flag"],
                    "high_52w": base_depth["high_52w"],
                    "base_depth_pct": base_depth["base_depth_pct"],
                    "pivot_test_count": pivot["pivot_test_count"],
                    "breakout_flag": breakout["breakout_flag"],
                    "close_location_in_range": breakout["close_location_in_range"],
                    "days_since_breakout": breakout["days_since_breakout"],
                    "distance_to_sma20_pct": pullback["distance_to_sma20_pct"],
                    "pullback_volume_ratio": pullback["pullback_volume_ratio"],
                    "support_rebound_flag": pullback["support_rebound_flag"],
                },
                "reasons": reasons,
                "signals": reasons,
            }
        )

    logger.info(
        "Bull engine filter diagnostics: total=%s missing_snapshot=%s static_threshold=%s missing_history=%s short_history=%s rs_fail=%s prior_uptrend_pass=%s prior_uptrend_fail=%s cwh_true=%s vcp_true=%s pattern_fail=%s accepted=%s",
        stats["total_rows"],
        stats["reject_missing_snapshot_fields"],
        stats["reject_static_thresholds"],
        stats["reject_missing_history"],
        stats["reject_short_history"],
        stats["reject_rs"],
        stats["prior_uptrend_pass"],
        stats["prior_uptrend_fail"],
        stats["cwh_candidate_count"],
        stats["vcp_candidate_count"],
        stats["reject_pattern"],
        stats["accepted"],
    )

    candidates.sort(
        key=lambda x: (
            _stage_sort_rank(str(x.get("pattern_stage", "early-stage"))),
            -float(_to_float(x.get("pattern_quality_score")) or 0.0),
            -float(_to_float(x.get("rs_score")) or 0.0),
            -float(_to_float(x.get("volume_quality_score")) or 0.0),
            -float(_to_float(x.get("score")) or 0.0),
        )
    )

    return candidates
