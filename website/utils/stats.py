from datetime import datetime
from math import ceil

from sqlalchemy import or_

from website import db
from website.models import (
    ROLE_CLIENT,
    ROLE_INSTRUCTOR,
    SESSION_CANCELLED,
    GymSession,
    GymSessionBooking,
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


def _chart_months(now, past_count=MONTH_WINDOW, future_count=1):
    months = _last_months(now, past_count)
    year, month = now.year, now.month
    for _ in range(future_count):
        nxt = _next_month_start(year, month)
        months.append((nxt.year, nxt.month))
        year, month = nxt.year, nxt.month
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
        "client_minutes": 0,
        "client_past_minutes": 0,
        "client_future_minutes": 0,
        "booked_count": 0,
        "open_count": 0,
        "clients": set(),
    }


def _query_sessions(now, months, instructor_id=None, client_id=None):
    window_start = _month_start(*months[0])
    window_end = _next_month_start(*months[-1])
    query = GymSession.query.filter(
        GymSession.status != SESSION_CANCELLED,
        GymSession.datetime_start >= window_start,
        GymSession.datetime_start < window_end,
    )
    if instructor_id is not None:
        query = query.filter(GymSession.instructor_id == instructor_id)
    if client_id is not None:
        booked_ids = db.session.query(GymSessionBooking.session_id).filter(
            GymSessionBooking.client_id == client_id
        )
        query = query.filter(
            or_(GymSession.client_id == client_id, GymSession.id.in_(booked_ids))
        )
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
        occupants = [client.id for client in session.booked_clients]
        is_work = bool(occupants)
        if client_only:
            client_minutes = minutes if occupants else 0
        else:
            client_minutes = minutes * len(occupants)
        bucket["client_minutes"] += client_minutes
        if is_past:
            bucket["client_past_minutes"] += client_minutes
        else:
            bucket["client_future_minutes"] += client_minutes
        if client_only or is_work:
            bucket["booked_minutes"] += minutes
            bucket["booked_count"] += 1
            if is_past:
                bucket["booked_past_minutes"] += minutes
            else:
                bucket["booked_future_minutes"] += minutes
            bucket["clients"].update(occupants)
        elif not client_only:
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
            "is_future": (year, month) > current,
            "booked": _format_duration(bucket["booked_minutes"]),
            "booked_hours": bucket["booked_minutes"] / 60.0,
            "booked_past_hours": bucket["booked_past_minutes"] / 60.0,
            "booked_future_hours": bucket["booked_future_minutes"] / 60.0,
            "client": _format_duration(bucket["client_minutes"]),
            "client_hours": bucket["client_minutes"] / 60.0,
            "client_past_hours": bucket["client_past_minutes"] / 60.0,
            "client_future_hours": bucket["client_future_minutes"] / 60.0,
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


def _chart_columns(row, include_open, kind="session"):
    """Return columns of stacked segments, bottom segment first."""
    split = row.get("is_current") or row.get("is_future")
    if kind == "client":
        if split:
            return [
                [
                    {
                        "key": "past client hours",
                        "hours": row.get("client_past_hours", 0.0),
                        "fill": COLOR_BOOKED_PAST,
                        "label_fill": "#ffffff",
                    },
                    {
                        "key": "upcoming client hours",
                        "hours": row.get("client_future_hours", 0.0),
                        "fill": COLOR_BOOKED_FUTURE,
                        "label_fill": "#102a3a",
                    },
                ]
            ]
        return [
            [
                {
                    "key": "client hours",
                    "hours": row.get("client_hours", 0.0),
                    "fill": COLOR_BOOKED_PAST,
                    "label_fill": "#ffffff",
                }
            ]
        ]
    if split:
        columns = [
            [
                {
                    "key": "past work",
                    "hours": row.get("booked_past_hours", 0.0),
                    "fill": COLOR_BOOKED_PAST,
                    "label_fill": "#ffffff",
                },
                {
                    "key": "upcoming work",
                    "hours": row.get("booked_future_hours", 0.0),
                    "fill": COLOR_BOOKED_FUTURE,
                    "label_fill": "#102a3a",
                },
            ]
        ]
        if include_open:
            columns.append(
                [
                    {
                        "key": "past unbooked",
                        "hours": row.get("open_past_hours", 0.0),
                        "fill": COLOR_UNBOOKED_PAST,
                        "label_fill": "#ffffff",
                    },
                    {
                        "key": "upcoming unbooked",
                        "hours": row.get("open_future_hours", 0.0),
                        "fill": COLOR_UNBOOKED_FUTURE,
                        "label_fill": "#102a3a",
                    },
                ]
            )
        return columns
    columns = [
        [
            {
                "key": "work",
                "hours": row["booked_hours"],
                "fill": COLOR_BOOKED_PAST,
                "label_fill": "#ffffff",
            }
        ]
    ]
    if include_open:
        columns.append(
            [
                {
                    "key": "unbooked",
                    "hours": row.get("open_hours", 0.0),
                    "fill": COLOR_UNBOOKED_PAST,
                    "label_fill": "#ffffff",
                }
            ]
        )
    return columns


def _chart_max_hours(rows, include_open, kind="session"):
    values = []
    for row in rows:
        for column in _chart_columns(row, include_open, kind):
            values.append(sum(item["hours"] for item in column))
    peak = max(values) if values else 0.0
    if peak <= 0:
        return 4.0
    return float(max(1, ceil(peak)))


def _build_chart(rows, include_open, kind="session"):
    width, height = 720, 280
    pad_l, pad_r, pad_t, pad_b = 48, 16, 28, 44
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    max_hours = _chart_max_hours(rows, include_open, kind)
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
        columns = _chart_columns(row, include_open, kind)
        bar_count = max(1, len(columns))
        inner = group_w * 0.72
        bar_gap = 4 if bar_count > 1 else 0
        bar_w = max(8.0, (inner - bar_gap * (bar_count - 1)) / bar_count)
        group_x = pad_l + group_w * index + (group_w - inner) / 2
        drawn = []
        stack_gap = 1.5
        baseline = pad_t + plot_h
        for col_index, column in enumerate(columns):
            x = group_x + col_index * (bar_w + bar_gap)
            cursor = baseline
            for bar in column:
                hours = bar["hours"]
                bar_h = 0.0 if max_hours <= 0 else plot_h * (hours / max_hours)
                if bar_h > 0 and cursor < baseline:
                    cursor -= stack_gap
                y = cursor - bar_h
                if bar_h >= 14:
                    label_y = y + bar_h / 2 + 3
                else:
                    label_y = y - 6
                drawn.append(
                    {
                        "x": round(x, 2),
                        "y": round(y, 2),
                        "width": round(bar_w, 2),
                        "height": round(max(bar_h, 0.0), 2),
                        "fill": bar["fill"],
                        "label": _format_hours_short(hours),
                        "label_fill": bar.get("label_fill", "#102a3a"),
                        "label_x": round(x + bar_w / 2, 2),
                        "label_y": round(max(pad_t + 10, label_y), 2),
                        "title": f"{row['label']} {bar['key']} {_format_hours_short(hours)}",
                    }
                )
                if bar_h > 0:
                    cursor = y
        if kind == "client":
            summary_parts = [f"{row['label']}: client hours {row.get('client', '0 h 0 min')}"]
            if row.get("is_current") or row.get("is_future"):
                summary_parts.append(
                    f"past {_format_hours_short(row.get('client_past_hours', 0))}, "
                    f"upcoming {_format_hours_short(row.get('client_future_hours', 0))}"
                )
        else:
            summary_parts = [f"{row['label']}: work {row['booked']}"]
            if row.get("is_current") or row.get("is_future"):
                summary_parts.append(
                    f"past work {_format_hours_short(row.get('booked_past_hours', 0))}, "
                    f"upcoming work {_format_hours_short(row.get('booked_future_hours', 0))}"
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
        "kind": kind,
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
        booked_ids = db.session.query(GymSessionBooking.session_id).filter(
            GymSessionBooking.client_id == client_id
        )
        query = query.filter(
            or_(GymSession.client_id == client_id, GymSession.id.in_(booked_ids))
        )
    return query.order_by(GymSession.datetime_start).limit(limit).all()


def _next_label(upcoming):
    if not upcoming:
        return "None yet"
    session = upcoming[0]
    return session.datetime_start.strftime("%a %d %b, %H:%M")


def _dashboard_charts(month_rows, show_session=True):
    client_chart = {
        "id": "client-hours",
        "title": "Client hours per month",
        "hint": "Hours clients spent in sessions. Two people in a one-hour class count as two hours. This month stacks past hours under upcoming hours. Next month shows upcoming hours.",
        "include_open": False,
        "kind": "client",
        "chart": _build_chart(month_rows, include_open=False, kind="client"),
    }
    charts = [client_chart]
    session_chart = None
    if show_session:
        session_chart = {
            "id": "session-hours",
            "title": "Working hours per month",
            "hint": "Calendar hours of sessions. A session counts as work if at least one client is booked. Unbooked is open time with no clients. This month stacks past hours under upcoming hours. Next month shows upcoming hours.",
            "include_open": True,
            "kind": "session",
            "chart": _build_chart(month_rows, include_open=True, kind="session"),
        }
        charts.append(session_chart)
    return charts, client_chart, session_chart


def instructor_dashboard(user, now):
    history = _last_months(now)
    months = _chart_months(now)
    sessions = _query_sessions(now, months, instructor_id=user.id)
    buckets = _fill_months(sessions, months, now)
    current = buckets[(now.year, now.month)]
    booked_values = [buckets[key]["booked_minutes"] for key in history]
    open_values = [buckets[key]["open_minutes"] for key in history]
    upcoming = _upcoming(now, instructor_id=user.id)
    month_rows = _month_rows(months, buckets, include_open=True, now=now)
    charts, client_chart, session_chart = _dashboard_charts(month_rows, show_session=True)
    return {
        "title": "Your teaching stats",
        "window_label": f"Last {MONTH_WINDOW} months and next month",
        "include_open": True,
        "cards": [
            {"label": "Booked this month", "value": _format_duration(current["booked_minutes"])},
            {"label": "Average booked / month", "value": _format_duration(_average(booked_values))},
            {"label": "Average unbooked / month", "value": _format_duration(_average(open_values))},
            {"label": "Next session", "value": _next_label(upcoming)},
        ],
        "months": month_rows,
        "charts": charts,
        "client_chart": client_chart["chart"],
        "chart": session_chart["chart"],
        "upcoming": upcoming,
    }


def client_dashboard(user, now):
    history = _last_months(now)
    months = _chart_months(now)
    sessions = _query_sessions(now, months, client_id=user.id)
    buckets = _fill_months(sessions, months, now, client_only=True)
    current = buckets[(now.year, now.month)]
    booked_values = [buckets[key]["booked_minutes"] for key in history]
    upcoming = _upcoming(now, client_id=user.id)
    month_rows = _month_rows(months, buckets, include_open=False, now=now)
    charts, client_chart, _session_chart = _dashboard_charts(month_rows, show_session=False)
    return {
        "title": "Your training stats",
        "window_label": f"Last {MONTH_WINDOW} months and next month",
        "include_open": False,
        "cards": [
            {"label": "Booked this month", "value": _format_duration(current["booked_minutes"])},
            {"label": "Average booked / month", "value": _format_duration(_average(booked_values))},
            {"label": "Sessions this month", "value": str(current["booked_count"])},
            {"label": "Next session", "value": _next_label(upcoming)},
        ],
        "months": month_rows,
        "charts": charts,
        "client_chart": client_chart["chart"],
        "chart": client_chart["chart"],
        "upcoming": upcoming,
    }


def client_hours_report(now):
    months = _last_months(now)
    sessions = _query_sessions(now, months)
    clients = (
        User.query.filter_by(role=ROLE_CLIENT)
        .order_by(User.name_last, User.name_first, User.email)
        .all()
    )
    totals = {client.id: {key: 0 for key in months} for client in clients}
    for session in sessions:
        key = (session.datetime_start.year, session.datetime_start.month)
        if key not in months:
            continue
        minutes = _minutes(session)
        for occupant in session.booked_clients:
            if occupant.id in totals:
                totals[occupant.id][key] += minutes
    month_headers = [
        {
            "key": f"{year}-{month:02d}",
            "label": datetime(year, month, 1).strftime("%b %Y"),
            "is_current": (year, month) == (now.year, now.month),
        }
        for year, month in months
    ]
    rows = []
    for client in clients:
        minutes_by_month = [totals[client.id][key] for key in months]
        total_minutes = sum(minutes_by_month)
        rows.append(
            {
                "id": client.id,
                "name": client.display_name,
                "email": client.email,
                "minutes": minutes_by_month,
                "hours": [_format_duration(value) for value in minutes_by_month],
                "total_minutes": total_minutes,
                "total": _format_duration(total_minutes),
            }
        )
    column_minutes = [
        sum(row["minutes"][index] for row in rows) for index in range(len(months))
    ]
    grand_minutes = sum(column_minutes)
    return {
        "title": "Client booked hours",
        "window_label": f"Last {MONTH_WINDOW} months",
        "months": month_headers,
        "rows": rows,
        "column_minutes": column_minutes,
        "column_totals": [_format_duration(value) for value in column_minutes],
        "grand_minutes": grand_minutes,
        "grand_total": _format_duration(grand_minutes),
    }


def admin_dashboard(now):
    history = _last_months(now)
    months = _chart_months(now)
    sessions = _query_sessions(now, months)
    buckets = _fill_months(sessions, months, now)
    current = buckets[(now.year, now.month)]
    booked_values = [buckets[key]["booked_minutes"] for key in history]
    open_values = [buckets[key]["open_minutes"] for key in history]
    upcoming = _upcoming(now, admin=True)
    month_rows = _month_rows(months, buckets, include_open=True, now=now)
    charts, client_chart, session_chart = _dashboard_charts(month_rows, show_session=True)
    return {
        "title": "Gym stats",
        "window_label": f"Last {MONTH_WINDOW} months and next month",
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
        "charts": charts,
        "client_chart": client_chart["chart"],
        "chart": session_chart["chart"],
        "upcoming": upcoming,
    }


def home_dashboard(user, now):
    if user.is_admin:
        return admin_dashboard(now)
    if user.is_instructor:
        return instructor_dashboard(user, now)
    return client_dashboard(user, now)
