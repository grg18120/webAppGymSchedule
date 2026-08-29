from datetime import datetime
from math import ceil

from website.models import (
    ROLE_CLIENT,
    ROLE_INSTRUCTOR,
    SESSION_AVAILABLE,
    SESSION_BOOKED,
    SESSION_CANCELLED,
    GymSession,
    User,
)

MONTH_WINDOW = 6


def _month_start(year, month):
    return datetime(year, month, 1)


def _next_month_start(year, month):
    if month == 12:
        return datetime(year + 1, 1, 1)
    return datetime(year, month + 1, 1)


def _last_months(now, count=MONTH_WINDOW):
    year, month = now.year, now.month
    months = []
    for _ in range(count):
        months.append((year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    months.reverse()
    return months


def _minutes(session):
    return max(0, session.duration_minutes)


def _format_duration(total_minutes):
    total = int(round(total_minutes))
    if total < 0:
        total = 0
    hours, minutes = divmod(total, 60)
    return f"{hours} h {minutes} min"


def _format_percent(part, whole):
    if whole <= 0:
        return "—"
    return f"{int(round(100 * part / whole))}%"


def _empty_bucket():
    return {
        "booked_minutes": 0,
        "open_minutes": 0,
        "booked_past_minutes": 0,
        "booked_future_minutes": 0,
        "open_past_minutes": 0,
        "open_future_minutes": 0,
        "booked_count": 0,
        "open_count": 0,
        "clients": set(),
    }


def _query_sessions(now, months, instructor_id=None, client_id=None):
    window_start = _month_start(*months[0])
    window_end = _next_month_start(now.year, now.month)
    query = GymSession.query.filter(
        GymSession.status != SESSION_CANCELLED,
        GymSession.datetime_start >= window_start,
        GymSession.datetime_start < window_end,
    )
    if instructor_id is not None:
        query = query.filter(GymSession.instructor_id == instructor_id)
    if client_id is not None:
        query = query.filter(GymSession.client_id == client_id, GymSession.status == SESSION_BOOKED)
    return query.all()


def _fill_months(sessions, months, now, client_only=False):
    buckets = {key: _empty_bucket() for key in months}
    for session in sessions:
        key = (session.datetime_start.year, session.datetime_start.month)
        bucket = buckets.get(key)
        if not bucket:
            continue
        minutes = _minutes(session)
        is_past = session.datetime_start <= now
        if session.status == SESSION_BOOKED:
            bucket["booked_minutes"] += minutes
            bucket["booked_count"] += 1
            if is_past:
                bucket["booked_past_minutes"] += minutes
            else:
                bucket["booked_future_minutes"] += minutes
            if session.client_id:
                bucket["clients"].add(session.client_id)
        elif not client_only and session.status == SESSION_AVAILABLE:
            if is_past:
                bucket["open_minutes"] += minutes
                bucket["open_past_minutes"] += minutes
                bucket["open_count"] += 1
            else:
                bucket["open_future_minutes"] += minutes
    return buckets


def _month_rows(months, buckets, include_open, now):
    current = (now.year, now.month)
    rows = []
    for year, month in months:
        bucket = buckets[(year, month)]
        row = {
            "label": datetime(year, month, 1).strftime("%b %Y"),
            "is_current": (year, month) == current,
            "booked": _format_duration(bucket["booked_minutes"]),
            "booked_hours": bucket["booked_minutes"] / 60.0,
            "booked_past_hours": bucket["booked_past_minutes"] / 60.0,
            "booked_future_hours": bucket["booked_future_minutes"] / 60.0,
        }
        if include_open:
            row["open"] = _format_duration(bucket["open_minutes"])
            row["open_hours"] = bucket["open_minutes"] / 60.0
            row["open_past_hours"] = bucket["open_past_minutes"] / 60.0
            row["open_future_hours"] = bucket["open_future_minutes"] / 60.0
        rows.append(row)
    return rows


def _average(values):
    if not values:
        return 0.0
    return sum(values) / len(values)


def _format_hours_short(hours):
    total = max(0.0, float(hours))
    if abs(total - round(total)) < 0.05:
        return f"{int(round(total))} h"
    return f"{total:.1f} h"


COLOR_BOOKED_PAST = "#1565c0"
COLOR_BOOKED_FUTURE = "#90caf9"
COLOR_UNBOOKED_PAST = "#2e7d32"
COLOR_UNBOOKED_FUTURE = "#a5d6a7"


def _chart_series(row, include_open):
    if row.get("is_current"):
        series = [
            {
                "key": "past booked",
                "hours": row.get("booked_past_hours", 0.0),
                "fill": COLOR_BOOKED_PAST,
            },
            {
                "key": "upcoming booked",
                "hours": row.get("booked_future_hours", 0.0),
                "fill": COLOR_BOOKED_FUTURE,
            },
        ]
        if include_open:
            series.extend(
                [
                    {
                        "key": "past unbooked",
                        "hours": row.get("open_past_hours", 0.0),
                        "fill": COLOR_UNBOOKED_PAST,
                    },
                    {
                        "key": "upcoming unbooked",
                        "hours": row.get("open_future_hours", 0.0),
                        "fill": COLOR_UNBOOKED_FUTURE,
                    },
                ]
            )
        return series
    series = [
        {
            "key": "booked",
            "hours": row["booked_hours"],
            "fill": COLOR_BOOKED_PAST,
        }
    ]
    if include_open:
        series.append(
            {
                "key": "unbooked",
                "hours": row.get("open_hours", 0.0),
                "fill": COLOR_UNBOOKED_PAST,
            }
        )
    return series


def _chart_max_hours(rows, include_open):
    values = []
    for row in rows:
        values.extend(item["hours"] for item in _chart_series(row, include_open))
    peak = max(values) if values else 0.0
    if peak <= 0:
        return 4.0
    return float(max(1, ceil(peak)))


def _build_chart(rows, include_open):
    width, height = 680, 280
    pad_l, pad_r, pad_t, pad_b = 48, 16, 28, 44
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    max_hours = _chart_max_hours(rows, include_open)
    tick_count = 4
    y_ticks = []
    for index in range(tick_count + 1):
        value = max_hours * index / tick_count
        y = pad_t + plot_h * (1 - index / tick_count)
        y_ticks.append({"value": _format_hours_short(value), "y": round(y, 2)})

    count = max(1, len(rows))
    group_w = plot_w / count
    groups = []
    for index, row in enumerate(rows):
        series = _chart_series(row, include_open)
        bar_count = max(1, len(series))
        inner = group_w * (0.9 if row.get("is_current") else 0.72)
        bar_gap = 3 if bar_count > 1 else 0
        bar_w = max(6.0, (inner - bar_gap * (bar_count - 1)) / bar_count)
        group_x = pad_l + group_w * index + (group_w - inner) / 2
        drawn = []
        for bar_index, bar in enumerate(series):
            hours = bar["hours"]
            bar_h = 0.0 if max_hours <= 0 else plot_h * (hours / max_hours)
            x = group_x + bar_index * (bar_w + bar_gap)
            y = pad_t + plot_h - bar_h
            label_y = y - 4 if bar_h > 18 else y - 6
            drawn.append(
                {
                    "x": round(x, 2),
                    "y": round(y, 2),
                    "width": round(bar_w, 2),
                    "height": round(max(bar_h, 0.0), 2),
                    "fill": bar["fill"],
                    "label": _format_hours_short(hours),
                    "label_x": round(x + bar_w / 2, 2),
                    "label_y": round(max(pad_t + 10, label_y), 2),
                    "title": f"{row['label']} {bar['key']} {_format_hours_short(hours)}",
                }
            )
        summary_parts = [f"{row['label']}: booked {row['booked']}"]
        if row.get("is_current"):
            summary_parts.append(
                f"past booked {_format_hours_short(row.get('booked_past_hours', 0))}, "
                f"upcoming booked {_format_hours_short(row.get('booked_future_hours', 0))}"
            )
            if include_open:
                summary_parts.append(
                    f"past unbooked {_format_hours_short(row.get('open_past_hours', 0))}, "
                    f"upcoming unbooked {_format_hours_short(row.get('open_future_hours', 0))}"
                )
        elif include_open:
            summary_parts.append(f"unbooked {row['open']}")
        groups.append(
            {
                "label": row["label"],
                "short_label": datetime.strptime(row["label"], "%b %Y").strftime("%b %y"),
                "label_x": round(group_x + inner / 2, 2),
                "label_y": height - 14,
                "bars": drawn,
                "summary": "; ".join(summary_parts),
            }
        )
    return {
        "width": width,
        "height": height,
        "plot_top": pad_t,
        "plot_bottom": pad_t + plot_h,
        "plot_left": pad_l,
        "plot_right": width - pad_r,
        "y_ticks": y_ticks,
        "groups": groups,
        "include_open": include_open,
    }


def _upcoming(now, instructor_id=None, client_id=None, admin=False, limit=5):
    query = GymSession.query.filter(
        GymSession.datetime_start >= now,
        GymSession.status != SESSION_CANCELLED,
    )
    if admin:
        pass
    elif instructor_id is not None:
        query = query.filter(GymSession.instructor_id == instructor_id)
    elif client_id is not None:
        query = query.filter(GymSession.client_id == client_id, GymSession.status == SESSION_BOOKED)
    return query.order_by(GymSession.datetime_start).limit(limit).all()


def _next_label(upcoming):
    if not upcoming:
        return "None yet"
    session = upcoming[0]
    return session.datetime_start.strftime("%a %d %b, %H:%M")


def instructor_dashboard(user, now):
    months = _last_months(now)
    sessions = _query_sessions(now, months, instructor_id=user.id)
    buckets = _fill_months(sessions, months, now)
    current = buckets[(now.year, now.month)]
    booked_values = [buckets[key]["booked_minutes"] for key in months]
    open_values = [buckets[key]["open_minutes"] for key in months]
    upcoming = _upcoming(now, instructor_id=user.id)
    upcoming_booked = sum(1 for session in upcoming if session.status == SESSION_BOOKED)
    month_rows = _month_rows(months, buckets, include_open=True, now=now)
    return {
        "title": "Your teaching stats",
        "window_label": f"Last {MONTH_WINDOW} months",
        "include_open": True,
        "cards": [
            {"label": "Booked this month", "value": _format_duration(current["booked_minutes"])},
            {"label": "Unbooked this month", "value": _format_duration(current["open_minutes"])},
            {"label": "Average booked / month", "value": _format_duration(_average(booked_values))},
            {"label": "Average unbooked / month", "value": _format_duration(_average(open_values))},
            {
                "label": "Fill rate this month",
                "value": _format_percent(
                    current["booked_minutes"],
                    current["booked_minutes"] + current["open_minutes"],
                ),
            },
            {"label": "Clients this month", "value": str(len(current["clients"]))},
            {"label": "Upcoming booked sessions", "value": str(upcoming_booked)},
            {"label": "Next session", "value": _next_label(upcoming)},
        ],
        "months": month_rows,
        "chart": _build_chart(month_rows, True),
        "upcoming": upcoming,
    }


def client_dashboard(user, now):
    months = _last_months(now)
    sessions = _query_sessions(now, months, client_id=user.id)
    buckets = _fill_months(sessions, months, now, client_only=True)
    current = buckets[(now.year, now.month)]
    booked_values = [buckets[key]["booked_minutes"] for key in months]
    upcoming = _upcoming(now, client_id=user.id)
    total_booked = sum(booked_values)
    month_rows = _month_rows(months, buckets, include_open=False, now=now)
    return {
        "title": "Your training stats",
        "window_label": f"Last {MONTH_WINDOW} months",
        "include_open": False,
        "cards": [
            {"label": "Booked this month", "value": _format_duration(current["booked_minutes"])},
            {"label": "Average booked / month", "value": _format_duration(_average(booked_values))},
            {"label": "Sessions this month", "value": str(current["booked_count"])},
            {"label": "Hours in the last 6 months", "value": _format_duration(total_booked)},
            {"label": "Upcoming sessions", "value": str(len(upcoming))},
            {"label": "Next session", "value": _next_label(upcoming)},
        ],
        "months": month_rows,
        "chart": _build_chart(month_rows, False),
        "upcoming": upcoming,
    }


def admin_dashboard(now):
    months = _last_months(now)
    sessions = _query_sessions(now, months)
    buckets = _fill_months(sessions, months, now)
    current = buckets[(now.year, now.month)]
    booked_values = [buckets[key]["booked_minutes"] for key in months]
    open_values = [buckets[key]["open_minutes"] for key in months]
    upcoming = _upcoming(now, admin=True)
    month_rows = _month_rows(months, buckets, include_open=True, now=now)
    return {
        "title": "Gym stats",
        "window_label": f"Last {MONTH_WINDOW} months",
        "include_open": True,
        "cards": [
            {"label": "Users", "value": str(User.query.count())},
            {
                "label": "Instructors",
                "value": str(User.query.filter_by(role=ROLE_INSTRUCTOR).count()),
            },
            {"label": "Clients", "value": str(User.query.filter_by(role=ROLE_CLIENT).count())},
            {"label": "Booked this month", "value": _format_duration(current["booked_minutes"])},
            {"label": "Unbooked this month", "value": _format_duration(current["open_minutes"])},
            {"label": "Average booked / month", "value": _format_duration(_average(booked_values))},
            {"label": "Average unbooked / month", "value": _format_duration(_average(open_values))},
            {
                "label": "Fill rate this month",
                "value": _format_percent(
                    current["booked_minutes"],
                    current["booked_minutes"] + current["open_minutes"],
                ),
            },
            {"label": "Active clients this month", "value": str(len(current["clients"]))},
            {"label": "Upcoming sessions", "value": str(len(upcoming))},
        ],
        "months": month_rows,
        "chart": _build_chart(month_rows, True),
        "upcoming": upcoming,
    }


def home_dashboard(user, now):
    if user.is_admin:
        return admin_dashboard(now)
    if user.is_instructor:
        return instructor_dashboard(user, now)
    return client_dashboard(user, now)
