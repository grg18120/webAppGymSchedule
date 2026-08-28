from datetime import datetime

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


def _hours(session):
    return session.duration_minutes / 60.0


def _format_hours(value):
    rounded = round(value, 1)
    if abs(rounded - round(rounded)) < 0.05:
        return f"{int(round(rounded))} h"
    return f"{rounded:.1f} h"


def _format_percent(part, whole):
    if whole <= 0:
        return "—"
    return f"{int(round(100 * part / whole))}%"


def _empty_bucket():
    return {
        "booked_hours": 0.0,
        "open_hours": 0.0,
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


def _fill_months(sessions, months, client_only=False):
    buckets = {key: _empty_bucket() for key in months}
    for session in sessions:
        key = (session.datetime_start.year, session.datetime_start.month)
        bucket = buckets.get(key)
        if not bucket:
            continue
        hours = _hours(session)
        if session.status == SESSION_BOOKED:
            bucket["booked_hours"] += hours
            bucket["booked_count"] += 1
            if session.client_id:
                bucket["clients"].add(session.client_id)
        elif not client_only and session.status == SESSION_AVAILABLE:
            bucket["open_hours"] += hours
            bucket["open_count"] += 1
    return buckets


def _month_rows(months, buckets, include_open):
    rows = []
    for year, month in months:
        bucket = buckets[(year, month)]
        row = {
            "label": datetime(year, month, 1).strftime("%b %Y"),
            "booked": _format_hours(bucket["booked_hours"]),
            "booked_hours": bucket["booked_hours"],
        }
        if include_open:
            row["open"] = _format_hours(bucket["open_hours"])
            row["open_hours"] = bucket["open_hours"]
        rows.append(row)
    return rows


def _average(values):
    if not values:
        return 0.0
    return sum(values) / len(values)


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
    buckets = _fill_months(sessions, months)
    current = buckets[(now.year, now.month)]
    booked_values = [buckets[key]["booked_hours"] for key in months]
    open_values = [buckets[key]["open_hours"] for key in months]
    upcoming = _upcoming(now, instructor_id=user.id)
    upcoming_booked = sum(1 for session in upcoming if session.status == SESSION_BOOKED)
    return {
        "title": "Your teaching stats",
        "window_label": f"Last {MONTH_WINDOW} months",
        "include_open": True,
        "cards": [
            {"label": "Booked this month", "value": _format_hours(current["booked_hours"])},
            {"label": "Unbooked this month", "value": _format_hours(current["open_hours"])},
            {"label": "Average booked / month", "value": _format_hours(_average(booked_values))},
            {"label": "Average unbooked / month", "value": _format_hours(_average(open_values))},
            {
                "label": "Fill rate this month",
                "value": _format_percent(
                    current["booked_hours"],
                    current["booked_hours"] + current["open_hours"],
                ),
            },
            {"label": "Clients this month", "value": str(len(current["clients"]))},
            {"label": "Upcoming booked sessions", "value": str(upcoming_booked)},
            {"label": "Next session", "value": _next_label(upcoming)},
        ],
        "months": _month_rows(months, buckets, include_open=True),
        "upcoming": upcoming,
    }


def client_dashboard(user, now):
    months = _last_months(now)
    sessions = _query_sessions(now, months, client_id=user.id)
    buckets = _fill_months(sessions, months, client_only=True)
    current = buckets[(now.year, now.month)]
    booked_values = [buckets[key]["booked_hours"] for key in months]
    upcoming = _upcoming(now, client_id=user.id)
    total_booked = sum(booked_values)
    return {
        "title": "Your training stats",
        "window_label": f"Last {MONTH_WINDOW} months",
        "include_open": False,
        "cards": [
            {"label": "Booked this month", "value": _format_hours(current["booked_hours"])},
            {"label": "Average booked / month", "value": _format_hours(_average(booked_values))},
            {"label": "Sessions this month", "value": str(current["booked_count"])},
            {"label": "Hours in the last 6 months", "value": _format_hours(total_booked)},
            {"label": "Upcoming sessions", "value": str(len(upcoming))},
            {"label": "Next session", "value": _next_label(upcoming)},
        ],
        "months": _month_rows(months, buckets, include_open=False),
        "upcoming": upcoming,
    }


def admin_dashboard(now):
    months = _last_months(now)
    sessions = _query_sessions(now, months)
    buckets = _fill_months(sessions, months)
    current = buckets[(now.year, now.month)]
    booked_values = [buckets[key]["booked_hours"] for key in months]
    open_values = [buckets[key]["open_hours"] for key in months]
    upcoming = _upcoming(now, admin=True)
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
            {"label": "Booked this month", "value": _format_hours(current["booked_hours"])},
            {"label": "Unbooked this month", "value": _format_hours(current["open_hours"])},
            {"label": "Average booked / month", "value": _format_hours(_average(booked_values))},
            {"label": "Average unbooked / month", "value": _format_hours(_average(open_values))},
            {
                "label": "Fill rate this month",
                "value": _format_percent(
                    current["booked_hours"],
                    current["booked_hours"] + current["open_hours"],
                ),
            },
            {"label": "Active clients this month", "value": str(len(current["clients"]))},
            {"label": "Upcoming sessions", "value": str(len(upcoming))},
        ],
        "months": _month_rows(months, buckets, include_open=True),
        "upcoming": upcoming,
    }


def home_dashboard(user, now):
    if user.is_admin:
        return admin_dashboard(now)
    if user.is_instructor:
        return instructor_dashboard(user, now)
    return client_dashboard(user, now)
