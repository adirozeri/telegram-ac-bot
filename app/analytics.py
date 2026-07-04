"""Usage & cost analytics derived from the ON/OFF event log.

On-time is the union of successful ON->OFF intervals (an open ON interval runs
to 'now'). Intervals are split at local midnights for correct per-day buckets.
Cost = ON-minutes x cost_per_min. Physical-remote use isn't counted (the
Switcher's own state can't be trusted) — only commands the app issued.
"""
import time
from datetime import datetime, timedelta

from . import db


def _intervals(events, now):
    """Pair successful ON/OFF events into (start, end) epoch intervals."""
    intervals = []
    open_start = None
    for e in events:
        if not e["success"]:
            continue
        if e["action"] == "ON":
            if open_start is None:  # ignore ON while already on
                open_start = e["ts"]
        elif e["action"] == "OFF":
            if open_start is not None:
                if e["ts"] > open_start:
                    intervals.append((open_start, e["ts"]))
                open_start = None
    if open_start is not None:  # still on -> runs to now
        intervals.append((open_start, now))
    return intervals


def _split_by_day(intervals):
    """Return {YYYY-MM-DD: seconds} splitting intervals across local midnights."""
    per_day = {}
    for start, end in intervals:
        cur = start
        while cur < end:
            day = datetime.fromtimestamp(cur)
            next_midnight = datetime(day.year, day.month, day.day) + timedelta(days=1)
            chunk_end = min(end, next_midnight.timestamp())
            key = day.strftime("%Y-%m-%d")
            per_day[key] = per_day.get(key, 0.0) + (chunk_end - cur)
            cur = chunk_end
    return per_day


def _seconds_in_range(intervals, start_ts, end_ts):
    total = 0.0
    for s, e in intervals:
        lo, hi = max(s, start_ts), min(e, end_ts)
        if hi > lo:
            total += hi - lo
    return total


def _minutes(seconds):
    return round(seconds / 60, 1)


def compute(now=None, days=30):
    now = now or time.time()
    events = db.get_events()
    intervals = _intervals(events, now)

    today = datetime.fromtimestamp(now)
    start_today = datetime(today.year, today.month, today.day).timestamp()
    start_week = start_today - 6 * 86400   # last 7 days incl. today
    start_month = start_today - 29 * 86400  # last 30 days

    per_day = _split_by_day(intervals)
    series = []
    for i in range(days - 1, -1, -1):
        d = datetime.fromtimestamp(start_today - i * 86400)
        key = d.strftime("%Y-%m-%d")
        series.append({"date": key, "minutes": round(per_day.get(key, 0.0) / 60, 1)})

    on_secs_today = _seconds_in_range(intervals, start_today, now)
    on_secs_week = _seconds_in_range(intervals, start_week, now)
    on_secs_month = _seconds_in_range(intervals, start_month, now)
    on_periods_today = sum(1 for s, e in intervals if e > start_today)

    try:
        cost_per_min = float(db.get_setting("cost_per_min", "0") or 0)
    except ValueError:
        cost_per_min = 0.0
    currency = db.get_setting("currency", "₪")

    n_periods = len(intervals)
    total_secs = sum(e - s for s, e in intervals)
    avg_period_min = _minutes(total_secs / n_periods) if n_periods else 0

    return {
        "today_min": _minutes(on_secs_today),
        "week_min": _minutes(on_secs_week),
        "month_min": _minutes(on_secs_month),
        "on_periods_today": on_periods_today,
        "on_periods_total": n_periods,
        "avg_period_min": avg_period_min,
        "series": series,
        "cost_per_min": cost_per_min,
        "currency": currency,
        "cost_today": round(on_secs_today / 60 * cost_per_min, 2),
        "cost_week": round(on_secs_week / 60 * cost_per_min, 2),
        "cost_month": round(on_secs_month / 60 * cost_per_min, 2),
    }
