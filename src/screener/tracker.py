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
        return {"active": [], "inactive": [], "dropped": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"active": [], "inactive": [], "dropped": []}

    if not isinstance(payload, dict):
        return {"active": [], "inactive": [], "dropped": []}

    active = payload.get("active")
    inactive = payload.get("inactive")
    dropped = payload.get("dropped")
    return {
        "active": active if isinstance(active, list) else [],
        "inactive": inactive if isinstance(inactive, list) else [],
        # backward compatibility with old payloads
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
        latest_open = None
        latest_low = None
        latest_high = None

        if df is not None and not df.empty:
            try:
                if "Volume" in df.columns:
                    avg_volume_50d = _to_float(df["Volume"].tail(50).mean())
                    latest_volume = _to_float(df["Volume"].iloc[-1])
                if "Open" in df.columns:
                    latest_open = _to_float(df["Open"].iloc[-1])
                if "High" in df.columns:
                    latest_high = _to_float(df["High"].iloc[-1])
                if "Low" in df.columns:
                    latest_low = _to_float(df["Low"].iloc[-1])
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
            "current_open": latest_open,
            "current_high": latest_high,
            "current_low": latest_low,
            "rsi14": _to_float(row.get("rsi14")),
            "distance_to_sma20_pct": distance_to_sma20,
            "volume_buzz_ratio": volume_buzz,
            "df_index": df.index if df is not None and not df.empty else None,
            "df": df if df is not None and not df.empty else None,
        }

    return out


def _resolve_entry_from_history(df: pd.DataFrame | None, capture_date: date, fallback: float | None) -> Tuple[str | None, float | None]:
    if df is None or df.empty:
        return None, fallback

    try:
        idx = pd.to_datetime(df.index)
        next_rows = df.loc[idx.date > capture_date]
        if next_rows.empty or "Open" not in next_rows.columns:
            return None, fallback
        entry_ts = pd.to_datetime(next_rows.index[0])
        entry_open = _to_float(next_rows["Open"].iloc[0])
        if entry_open is None or entry_open <= 0:
            return entry_ts.date().isoformat(), fallback
        return entry_ts.date().isoformat(), entry_open
    except Exception:  # noqa: BLE001
        return None, fallback


def _new_tracker_record(candidate: Dict[str, Any], current_date: date, latest: Dict[str, Any]) -> Dict[str, Any]:
    capture_close = _to_float(candidate.get("close"))
    current_close = _to_float(latest.get("current_close"))
    if current_close is None:
        current_close = capture_close

    risk = candidate.get("risk") if isinstance(candidate.get("risk"), dict) else {}
    atr14 = _to_float((risk or {}).get("atr14"))
    signal_close = _to_float((risk or {}).get("signal_close"))
    if signal_close is None:
        signal_close = _to_float((risk or {}).get("entry_reference"))
    if signal_close is None:
        signal_close = capture_close

    sl_level = _to_float((risk or {}).get("stop_loss"))
    if sl_level is None and atr14 is not None and signal_close is not None:
        sl_level = signal_close - (2.0 * atr14)

    activation_level = _to_float((risk or {}).get("activation_level"))
    if activation_level is None and atr14 is not None and signal_close is not None:
        activation_level = signal_close + (2.0 * atr14)

    trailing_stop_offset = _to_float((risk or {}).get("trailing_stop_offset"))
    if trailing_stop_offset is None and atr14 is not None:
        trailing_stop_offset = 1.5 * atr14

    entry_date_utc, entry_price = _resolve_entry_from_history(
        latest.get("df"),
        current_date,
        _to_float((risk or {}).get("entry_reference")) or signal_close,
    )

    return {
        "symbol": _symbol_from_candidate(candidate),
        "capture_date_utc": current_date.isoformat(),
        "entry_date_utc": entry_date_utc,
        "entry_price": entry_price,
        "capture_close": capture_close,
        "current_close": current_close,
        "return_since_capture_pct": None,
        "days_tracked_trading": 1,
        "expiry_date_utc": None,
        "status": "active",
        "position_state": "active",
        "status_tag": "watching",
        "status_tags": ["watching"],
        "rank_at_capture": int(_to_float(candidate.get("rank")) or 0),
        "score_at_capture": _to_float(candidate.get("score")),
        "distance_to_sma20_pct": _to_float(latest.get("distance_to_sma20_pct")),
        "rsi14": _to_float(latest.get("rsi14")),
        "volume_buzz_ratio": _to_float(latest.get("volume_buzz_ratio")),
        "signal_close": signal_close,
        "signal_atr14": atr14,
        "stop_loss": sl_level,
        "activation_level": activation_level,
        "trailing_stop_offset": trailing_stop_offset,
        "trail_stop_price": None,
        "activated": False,
        "activation_date_utc": None,
        "activation_price": None,
        "highest_close_since_entry": None,
        "exit_reason": None,
        "exit_date_utc": None,
        "exit_price": None,
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

    entry_date = _extract_date(out.get("entry_date_utc"))
    entry_price = _to_float(out.get("entry_price"))
    stop_loss = _to_float(out.get("stop_loss"))
    activation_level = _to_float(out.get("activation_level"))
    trailing_stop_offset = _to_float(out.get("trailing_stop_offset"))

    df = latest.get("df")
    bars: List[Tuple[date, float | None, float | None, float | None, float | None]] = []
    if df is not None and isinstance(df, pd.DataFrame) and not df.empty and entry_date is not None:
        try:
            frame = df.copy().sort_index()
            for ts, row in frame.iterrows():
                d = pd.Timestamp(ts).date()
                if d < entry_date or d > current_date:
                    continue
                bars.append(
                    (
                        d,
                        _to_float(row.get("Open")),
                        _to_float(row.get("High")),
                        _to_float(row.get("Low")),
                        _to_float(row.get("Close")),
                    )
                )
        except Exception:  # noqa: BLE001
            bars = []

    activated = bool(out.get("activated"))
    activation_date_utc = _normalize_iso_date(out.get("activation_date_utc"))
    activation_price = _to_float(out.get("activation_price"))
    highest_close = _to_float(out.get("highest_close_since_entry"))

    position_state = "active"
    status_tags: List[str] = []
    exit_reason = out.get("exit_reason")
    exit_date_utc = _normalize_iso_date(out.get("exit_date_utc"))
    exit_price = _to_float(out.get("exit_price"))

    if entry_price is None or entry_price <= 0 or entry_date is None:
        position_state = "active"
        status_tags.append("entry_pending")
    else:
        max_hold_days = 15
        trade_days = 0
        for d, open_px, _high_px, low_px, close_px in bars:
            trade_days += 1

            if close_px is not None:
                if highest_close is None:
                    highest_close = close_px
                else:
                    highest_close = max(highest_close, close_px)

            if not activated:
                if stop_loss is not None and open_px is not None and open_px <= stop_loss:
                    position_state = "inactive"
                    exit_reason = "sl_gap_open"
                    exit_date_utc = d.isoformat()
                    exit_price = open_px
                    status_tags.append("stop_loss")
                    break
                if stop_loss is not None and low_px is not None and low_px <= stop_loss:
                    position_state = "inactive"
                    exit_reason = "sl_intraday"
                    exit_date_utc = d.isoformat()
                    exit_price = stop_loss
                    status_tags.append("stop_loss")
                    break
                if activation_level is not None and close_px is not None and close_px >= activation_level:
                    activated = True
                    activation_date_utc = d.isoformat()
                    activation_price = close_px
                    status_tags.append("trail_stop")
            else:
                if trailing_stop_offset is not None and highest_close is not None and close_px is not None:
                    trail_stop = highest_close - trailing_stop_offset
                    out["trail_stop_price"] = trail_stop
                    if close_px <= trail_stop:
                        position_state = "inactive"
                        exit_reason = "trailing_stop_close"
                        exit_date_utc = d.isoformat()
                        exit_price = close_px
                        status_tags.append("trail_stop_hit")
                        break

            if trade_days >= max_hold_days:
                if close_px is not None:
                    position_state = "inactive"
                    exit_reason = "time_stop_day_15_close"
                    exit_date_utc = d.isoformat()
                    exit_price = close_px
                    status_tags.append("time_stop")
                break

    if activated and "trail_stop" not in status_tags:
        status_tags.append("trail_stop")

    if position_state == "active" and not status_tags:
        status_tags.append("watching")

    out["activated"] = activated
    out["activation_date_utc"] = activation_date_utc
    out["activation_price"] = activation_price
    out["highest_close_since_entry"] = highest_close
    out["position_state"] = position_state
    out["status"] = position_state
    out["status_tags"] = status_tags
    out["status_tag"] = status_tags[0] if status_tags else "watching"
    out["exit_reason"] = exit_reason
    out["exit_date_utc"] = exit_date_utc
    out["exit_price"] = exit_price

    out["capture_date_utc"] = _normalize_iso_date(out.get("capture_date_utc"))
    out["entry_date_utc"] = _normalize_iso_date(out.get("entry_date_utc"))
    out["last_updated_utc"] = _iso_now_utc()
    return out


def _clean_record(record: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(record)
    out["symbol"] = str(out.get("symbol") or "").strip().upper()
    out["capture_date_utc"] = _normalize_iso_date(out.get("capture_date_utc"))
    out["entry_date_utc"] = _normalize_iso_date(out.get("entry_date_utc"))
    out["expiry_date_utc"] = _normalize_iso_date(out.get("expiry_date_utc"))

    raw_status = str(out.get("status") or out.get("position_state") or "active").lower()
    if raw_status in {"inactive", "dropped"}:
        out["status"] = "inactive"
        out["position_state"] = "inactive"
    else:
        out["status"] = "active"
        out["position_state"] = "active"

    if not isinstance(out.get("status_tags"), list):
        single_tag = str(out.get("status_tag") or "").strip()
        out["status_tags"] = [single_tag] if single_tag else []
    if not out.get("status_tag"):
        tags = out.get("status_tags") or []
        out["status_tag"] = str(tags[0]) if tags else "watching"

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
    inactive_existing = [_clean_record(r) for r in existing.get("inactive", []) if str(r.get("symbol") or "").strip()]
    dropped_existing = [_clean_record(r) for r in existing.get("dropped", []) if str(r.get("symbol") or "").strip()]

    latest_by_symbol = _build_latest_metrics_map(rows_with_metrics, enriched_by_yf_symbol)

    active_map: Dict[str, Dict[str, Any]] = {
        str(r.get("symbol") or "").strip().upper(): r for r in active_existing if str(r.get("symbol") or "").strip()
    }
    inactive_map: Dict[str, Dict[str, Any]] = {
        str(r.get("symbol") or "").strip().upper(): r
        for r in (inactive_existing + dropped_existing)
        if str(r.get("symbol") or "").strip()
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
            "df": None,
        }

        if symbol in active_map or symbol in inactive_map:
            continue

        active_map[symbol] = _new_tracker_record(candidate, current_date=current_date, latest=latest)

    refreshed_active: List[Dict[str, Any]] = []
    refreshed_inactive: List[Dict[str, Any]] = []

    for symbol, record in {**inactive_map, **active_map}.items():
        latest = latest_by_symbol.get(symbol) or {
            "current_close": _to_float(record.get("current_close")),
            "rsi14": _to_float(record.get("rsi14")),
            "distance_to_sma20_pct": _to_float(record.get("distance_to_sma20_pct")),
            "volume_buzz_ratio": _to_float(record.get("volume_buzz_ratio")),
            "df_index": None,
            "df": None,
        }
        updated = _refresh_record(record, latest=latest, current_date=current_date)
        if str(updated.get("position_state") or "active").lower() == "inactive":
            refreshed_inactive.append(updated)
        else:
            refreshed_active.append(updated)

    refreshed_inactive.sort(key=lambda r: str(r.get("last_updated_utc") or ""), reverse=True)
    refreshed_inactive = refreshed_inactive[:MAX_DROPPED_HISTORY]

    refreshed_active.sort(
        key=lambda r: (
            _extract_date(r.get("capture_date_utc")) or date.min,
            str(r.get("symbol") or ""),
        ),
        reverse=True,
    )

    items = refreshed_active + refreshed_inactive

    payload = {
        "meta": {
            "generated_at_utc": _iso_now_utc(),
            "rules": {
                "engine": "bull",
                "max_rank": 10,
                "require_tags": ["🏆", "⚡"],
                "position_state": "active until stop-loss/trailing-stop/time-stop; inactive after exit",
            },
            "counts": {
                "active": len(refreshed_active),
                "inactive": len(refreshed_inactive),
                "items": len(items),
            },
        },
        "active": refreshed_active,
        "inactive": refreshed_inactive,
        # backward-compatibility alias for legacy UI
        "dropped": refreshed_inactive,
        "items": items,
    }

    tracker_path.parent.mkdir(parents=True, exist_ok=True)
    tracker_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
