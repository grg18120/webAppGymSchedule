from datetime import datetime, timedelta

from website.models import SESSION_CANCELLED, GymSession

START_HOUR = 6
END_HOUR = 23
HOURS = tuple(range(START_HOUR, END_HOUR))
HOUR_HEIGHT_PX = 48


def monday_of(day_date):
    return day_date - timedelta(days=day_date.weekday())


def week_dates(monday):
    return [monday + timedelta(days=offset) for offset in range(7)]


def visible_sessions(actor, range_start, range_end, instructor_id=None):
    query = GymSession.query.filter(
        GymSession.status != SESSION_CANCELLED,
        GymSession.datetime_start < range_end,
        GymSession.datetime_end > range_start,
    )
    if instructor_id:
        query = query.filter(GymSession.instructor_id == instructor_id)
    elif actor.is_instructor:
        query = query.filter(GymSession.instructor_id == actor.id)
    sessions = query.order_by(GymSession.datetime_start, GymSession.id).all()
    if actor.is_client:
        return [session for session in sessions if session.is_available or session.client_id == actor.id]
    return sessions


def _block_for_day(session, day_date):
    range_start = datetime(day_date.year, day_date.month, day_date.day, START_HOUR)
    range_end = datetime(day_date.year, day_date.month, day_date.day, END_HOUR)
    start = max(session.datetime_start, range_start)
    end = min(session.datetime_end, range_end)
    if end <= start:
        return None
    total = (range_end - range_start).total_seconds()
    top = (start - range_start).total_seconds() / total * 100
    height = (end - start).total_seconds() / total * 100
    return {
        "session": session,
        "start": start,
        "end": end,
        "top": round(top, 2),
        "height": round(max(height, 3.2), 2),
        "col": 0,
        "cols": 1,
    }


def _layout_overlaps(blocks):
    for block in blocks:
        overlapping = [
            other
            for other in blocks
            if other["start"] < block["end"] and other["end"] > block["start"]
        ]
        overlapping.sort(key=lambda item: (item["start"], item["session"].id))
        block["cols"] = len(overlapping)
        block["col"] = overlapping.index(block)
    return blocks


def days_with_blocks(actor, monday, instructor_id=None):
    dates = week_dates(monday)
    range_start = datetime(dates[0].year, dates[0].month, dates[0].day, START_HOUR)
    range_end = datetime(dates[-1].year, dates[-1].month, dates[-1].day, END_HOUR)
    sessions = visible_sessions(actor, range_start, range_end, instructor_id)
    days = []
    for day_date in dates:
        day_sessions = [
            session
            for session in sessions
            if session.datetime_start.date() == day_date or session.datetime_end.date() == day_date
        ]
        blocks = []
        for session in day_sessions:
            block = _block_for_day(session, day_date)
            if block:
                blocks.append(block)
        days.append(
            {
                "date": day_date,
                "label": day_date.strftime("%a"),
                "day_number": day_date.strftime("%d %b"),
                "blocks": _layout_overlaps(blocks),
            }
        )
    return days
