from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd


TRACKER_PATH = Path("docs/data/tracker.json")
TRACKING_WINDOW_TRADING_DAYS = 10
MAX_DROPPED_HISTORY = 300


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        v = float(value)
        if np.isnan(v) or np.isinf(v):
            return None
        return v
    except Exception:  # noqa: BLE001
        return None


def _today_utc_date() -> date:
    return datetime.now(timezone.utc).date()


def _iso_now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = text[:10]
    try:
        return date.fromisoformat(text)
    except Exception:  # noqa: BLE001
        return None


def _normalize_iso_date(value: Any) -> str | None:
    d = _extract_date(value)
    if d is None:
        return None
    return d.isoformat()


def _safe_read_tracker(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"active": [], "dropped": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"active": [], "dropped": []}

    if not isinstance(payload, dict):
        return {"active": [], "dropped": []}

    active = payload.get("active")
    dropped = payload.get("dropped")
    return {
        "active": active if isinstance(active, list) else [],
        "dropped": dropped if isinstance(dropped, list) else [],
    }


def _business_day_fallback(capture_date: date, current_date: date) -> Tuple[int, str]:
    if current_date < capture_date:
        return 0, capture_date.isoformat()

    days = int(np.busday_count(capture_date.isoformat(), current_date.isoformat())) + 1
    expiry_date = np.busday_offset(capture_date.isoformat(), TRACKING_WINDOW_TRADING_DAYS - 1, roll="forward")
    return max(days, 0), str(expiry_date)


def _compute_trading_day_stats(index: pd.Index, capture_date_raw: Any, current_date: date) -> Tuple[int, str | None]:
    capture_date = _extract_date(capture_date_raw)
    if capture_date is None:
        return 0, None

    if index is None or len(index) == 0:
        return _business_day_fallback(capture_date, current_date)

    dates = [ts.date() for ts in pd.to_datetime(index).to_pydatetime()]
    dates = sorted(set(dates))

    if not dates:
        return _business_day_fallback(capture_date, current_date)

    start_candidates = [d for d in dates if d >= capture_date]
    if not start_candidates:
        return _business_day_fallback(capture_date, current_date)

    start_date = start_candidates[0]
    visible = [d for d in dates if start_date <= d <= current_date]
    if not visible:
        return 0, start_date.isoformat()

    start_idx = dates.index(start_date)
    expiry_idx = start_idx + (TRACKING_WINDOW_TRADING_DAYS - 1)
    expiry_date = dates[expiry_idx].isoformat() if expiry_idx < len(dates) else None

    return len(visible), expiry_date


def _symbol_from_candidate(candidate: Dict[str, Any]) -> str:
    return str(candidate.get("symbol") or "").strip().upper()


def _is_tracker_eligible(candidate: Dict[str, Any]) -> bool:
    if str(candidate.get("engine") or "").lower() != "bull":
        return False

    rank = _to_float(candidate.get("rank"))
    if rank is None or rank > 10:
        return False

    leadership = _to_float(candidate.get("leadership_score"))
    actionability = _to_float(candidate.get("actionability_score"))

    has_trophy = leadership is not None and leadership >= 0.90
    has_lightning = actionability is not None and actionability >= 0.58
    return has_trophy and has_lightning


def _build_latest_metrics_map(rows: Iterable[Dict[str, Any]], enriched: Dict[str, pd.DataFrame]) -> Dict[str, Dict[str, Any]]:
    row_by_symbol = {str(r.get("symbol") or "").strip().upper(): r for r in rows}
    out: Dict[str, Dict[str, Any]] = {}

    for symbol, row in row_by_symbol.items():
        yf_symbol = str(row.get("yf_symbol") or symbol).strip()
        df = enriched.get(yf_symbol)

        latest_volume = _to_float(row.get("volume"))
        avg_volume_50d = None
        latest_close = _to_float(row.get("close"))

        if df is not None and not df.empty:
            try:
                if "Volume" in df.columns:
                    avg_volume_50d = _to_float(df["Volume"].tail(50).mean())
                    latest_volume = _to_float(df["Volume"].iloc[-1])
                if "Close" in df.columns:
                    latest_close = _to_float(df["Close"].iloc[-1])
            except Exception:  # noqa: BLE001
                pass

        volume_buzz = None
        if avg_volume_50d not in (None, 0.0) and latest_volume is not None:
            volume_buzz = latest_volume / avg_volume_50d

        sma20 = _to_float(row.get("sma20"))
        distance_to_sma20 = None
        if sma20 not in (None, 0.0) and latest_close is not None:
            distance_to_sma20 = (latest_close / sma20) - 1.0

        out[symbol] = {
            "symbol": symbol,
            "yf_symbol": yf_symbol,
            "current_close": latest_close,
            "rsi14": _to_float(row.get("rsi14")),
            "distance_to_sma20_pct": distance_to_sma20,
            "volume_buzz_ratio": volume_buzz,
            "df_index": df.index if df is not None and not df.empty else None,
        }

    return out


def _new_tracker_record(candidate: Dict[str, Any], current_date: date, latest: Dict[str, Any]) -> Dict[str, Any]:
    capture_close = _to_float(candidate.get("close"))
    current_close = _to_float(latest.get("current_close"))
    if current_close is None:
        current_close = capture_close

    return {
        "symbol": _symbol_from_candidate(candidate),
        "capture_date_utc": current_date.isoformat(),
        "capture_close": capture_close,
        "current_close": current_close,
        "return_since_capture_pct": None,
        "days_tracked_trading": 1,
        "expiry_date_utc": None,
        "status": "active",
        "rank_at_capture": int(_to_float(candidate.get("rank")) or 0),
        "score_at_capture": _to_float(candidate.get("score")),
        "distance_to_sma20_pct": _to_float(latest.get("distance_to_sma20_pct")),
        "rsi14": _to_float(latest.get("rsi14")),
        "volume_buzz_ratio": _to_float(latest.get("volume_buzz_ratio")),
        "last_updated_utc": _iso_now_utc(),
    }


def _refresh_record(record: Dict[str, Any], latest: Dict[str, Any], current_date: date) -> Dict[str, Any]:
    out = dict(record)
    capture_close = _to_float(out.get("capture_close"))

    current_close = _to_float(latest.get("current_close"))
    if current_close is not None:
        out["current_close"] = current_close

    if capture_close not in (None, 0.0) and _to_float(out.get("current_close")) is not None:
        out["return_since_capture_pct"] = (_to_float(out.get("current_close")) / capture_close) - 1.0
    else:
        out["return_since_capture_pct"] = None

    days_tracked, expiry_date = _compute_trading_day_stats(
        index=latest.get("df_index"),
        capture_date_raw=out.get("capture_date_utc"),
        current_date=current_date,
    )
    out["days_tracked_trading"] = int(days_tracked)
    out["expiry_date_utc"] = expiry_date

    out["distance_to_sma20_pct"] = _to_float(latest.get("distance_to_sma20_pct"))
    out["rsi14"] = _to_float(latest.get("rsi14"))
    out["volume_buzz_ratio"] = _to_float(latest.get("volume_buzz_ratio"))
    out["last_updated_utc"] = _iso_now_utc()

    if days_tracked > TRACKING_WINDOW_TRADING_DAYS:
        out["status"] = "dropped"
    else:
        out["status"] = "active"

    out["capture_date_utc"] = _normalize_iso_date(out.get("capture_date_utc"))
    return out


def _clean_record(record: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(record)
    out["symbol"] = str(out.get("symbol") or "").strip().upper()
    out["capture_date_utc"] = _normalize_iso_date(out.get("capture_date_utc"))
    out["expiry_date_utc"] = _normalize_iso_date(out.get("expiry_date_utc"))
    out["status"] = "dropped" if str(out.get("status") or "").lower() == "dropped" else "active"
    return out


def update_tracker_file(
    ranked_candidates: List[Dict[str, Any]],
    rows_with_metrics: List[Dict[str, Any]],
    enriched_by_yf_symbol: Dict[str, pd.DataFrame],
    tracker_path: Path = TRACKER_PATH,
) -> Dict[str, Any]:
    """Update tracker JSON without modifying existing screener payload contracts."""

    current_date = _today_utc_date()
    existing = _safe_read_tracker(tracker_path)

    active_existing = [_clean_record(r) for r in existing.get("active", []) if str(r.get("symbol") or "").strip()]
    dropped_existing = [_clean_record(r) for r in existing.get("dropped", []) if str(r.get("symbol") or "").strip()]

    latest_by_symbol = _build_latest_metrics_map(rows_with_metrics, enriched_by_yf_symbol)

    active_map: Dict[str, Dict[str, Any]] = {
        str(r.get("symbol") or "").strip().upper(): r for r in active_existing if str(r.get("symbol") or "").strip()
    }

    eligible_candidates = [c for c in ranked_candidates if _is_tracker_eligible(c)]

    for candidate in eligible_candidates:
        symbol = _symbol_from_candidate(candidate)
        if not symbol:
            continue

        latest = latest_by_symbol.get(symbol) or {
            "current_close": _to_float(candidate.get("close")),
            "rsi14": _to_float(candidate.get("rsi14")),
            "distance_to_sma20_pct": None,
            "volume_buzz_ratio": None,
            "df_index": None,
        }

        if symbol in active_map:
            continue

        active_map[symbol] = _new_tracker_record(candidate, current_date=current_date, latest=latest)

    refreshed_active: List[Dict[str, Any]] = []
    dropped_now: List[Dict[str, Any]] = []

    for symbol, record in active_map.items():
        latest = latest_by_symbol.get(symbol) or {
            "current_close": _to_float(record.get("current_close")),
            "rsi14": _to_float(record.get("rsi14")),
            "distance_to_sma20_pct": _to_float(record.get("distance_to_sma20_pct")),
            "volume_buzz_ratio": _to_float(record.get("volume_buzz_ratio")),
            "df_index": None,
        }
        updated = _refresh_record(record, latest=latest, current_date=current_date)
        if updated.get("status") == "dropped":
            dropped_now.append(updated)
        else:
            refreshed_active.append(updated)

    dropped_merged = [
        {**d, "status": "dropped", "last_updated_utc": _iso_now_utc()} for d in (dropped_now + dropped_existing)
    ]
    dropped_merged.sort(key=lambda r: str(r.get("last_updated_utc") or ""), reverse=True)
    dropped_merged = dropped_merged[:MAX_DROPPED_HISTORY]

    refreshed_active.sort(
        key=lambda r: (
            _extract_date(r.get("capture_date_utc")) or date.min,
            str(r.get("symbol") or ""),
        ),
        reverse=True,
    )

    items = refreshed_active + dropped_merged

    payload = {
        "meta": {
            "generated_at_utc": _iso_now_utc(),
            "rules": {
                "engine": "bull",
                "max_rank": 10,
                "require_tags": ["🏆", "⚡"],
                "drop_after_trading_days": TRACKING_WINDOW_TRADING_DAYS,
            },
            "counts": {
                "active": len(refreshed_active),
                "dropped": len(dropped_merged),
                "items": len(items),
            },
        },
        "active": refreshed_active,
        "dropped": dropped_merged,
        "items": items,
    }

    tracker_path.parent.mkdir(parents=True, exist_ok=True)
    tracker_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
