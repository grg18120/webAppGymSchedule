from datetime import datetime, timedelta

from website.models import SESSION_AVAILABLE, SESSION_BOOKED, SESSION_CANCELLED, GymSession

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
        return [session for session in sessions if session.is_available or session.is_booked_by(actor)]
    return sessions


def editor_payload(session, actor):
    start = session.datetime_start
    end = session.datetime_end
    end_hour, end_minute = end.hour, end.minute
    if end.date() > start.date() and end.hour == 0 and end.minute == 0:
        end_hour, end_minute = 24, 0
    can_manage = actor.is_admin or (actor.is_instructor and session.instructor_id == actor.id)
    data = {
        "id": session.id,
        "status": session.status,
        "status_label": session.status_label,
        "is_past": session.is_past,
        "position_count": int(session.position_count or 1),
        "booked_count": session.booked_count,
        "start_hour": start.hour,
        "start_minute": start.minute,
        "end_hour": end_hour,
        "end_minute": end_minute,
        "date_label": start.strftime("%A %d %B %Y"),
        "time_label": f"{start.strftime('%H:%M')} – {end.strftime('%H:%M')}",
        "instructor": session.instructor.display_name if session.instructor else "",
        "clients": [
            {"id": client.id, "name": client.display_name}
            for client in session.booked_clients
        ],
        "can_manage": can_manage,
        "can_book": bool(
            actor.is_client and session.is_available and not session.is_booked_by(actor)
        ),
        "can_cancel_own": bool(
            actor.is_client and session.is_booked_by(actor) and not session.is_past
        ),
        "can_delete": bool(
            can_manage
            and session.status == SESSION_AVAILABLE
            and session.booked_count == 0
            and (not session.is_past or actor.is_admin)
        ),
        "can_cancel_all": bool(can_manage and session.booked_count > 0 and not session.is_past),
        "can_delete_booked": bool(
            actor.is_admin and session.status == SESSION_BOOKED and session.is_past
        ),
    }
    if can_manage:
        data["edit_url"] = f"/sessions/{session.id}/edit"
        data["assign_url"] = f"/sessions/{session.id}/assign"
        data["unassign_url"] = f"/sessions/{session.id}/unassign"
        if data["can_cancel_all"]:
            data["cancel_url"] = f"/sessions/{session.id}/cancel"
        if data["can_delete"]:
            data["remove_url"] = f"/sessions/{session.id}/remove"
        if data["can_delete_booked"]:
            data["delete_url"] = f"/sessions/{session.id}/delete"
    if actor.is_client:
        if data["can_book"]:
            data["book_url"] = f"/sessions/{session.id}/book"
        if data["can_cancel_own"]:
            data["cancel_url"] = f"/sessions/{session.id}/cancel"
    return data


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
                block["editor"] = editor_payload(session, actor)
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
