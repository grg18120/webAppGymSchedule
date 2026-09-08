from datetime import datetime, timedelta

from website.models import SESSION_AVAILABLE, SESSION_BOOKED, SESSION_CANCELLED, GymSession

START_HOUR = 6
END_HOUR = 23
HOURS = tuple(range(START_HOUR, END_HOUR))
HOUR_HEIGHT_PX = 48


def now_line_percent(now, start_hour=START_HOUR, end_hour=END_HOUR):
    """Percent from the top of the day grid for a gym-local datetime, or None."""
    if now is None:
        return None
    start = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    end = now.replace(hour=end_hour, minute=0, second=0, microsecond=0)
    if now < start or now > end:
        return None
    total = (end - start).total_seconds()
    if total <= 0:
        return None
    return round(100.0 * (now - start).total_seconds() / total, 4)


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
        return [
            session
            for session in sessions
            if session.is_available
            or session.is_booked_by(actor)
            or (session.is_full and not session.is_past)
        ]
    return sessions


def editor_payload(session, actor):
    start = session.datetime_start
    end = session.datetime_end
    end_hour, end_minute = end.hour, end.minute
    if end.date() > start.date() and end.hour == 0 and end.minute == 0:
        end_hour, end_minute = 24, 0
    can_manage = actor.is_admin or (actor.is_instructor and session.instructor_id == actor.id)
    booked_by_me = bool(actor.is_client and session.is_booked_by(actor))
    interested_by_me = bool(actor.is_client and session.is_interested_by(actor))
    can_interest = bool(
        actor.is_client
        and session.is_full
        and not session.is_past
        and not booked_by_me
        and session.status != SESSION_CANCELLED
    )
    if actor.is_client:
        if booked_by_me:
            display_status = "booked"
            display_status_label = "Past booking" if session.is_past else "Your booking"
        elif session.is_full:
            display_status = "booked"
            display_status_label = "Full"
        else:
            display_status = "available"
            display_status_label = "Past open" if session.is_past else "Open slot"
        show_partial = False
    else:
        display_status = session.status
        display_status_label = session.status_label
        show_partial = session.is_partial
    data = {
        "id": session.id,
        "status": session.status,
        "status_label": display_status_label if actor.is_client else session.status_label,
        "is_past": session.is_past,
        "position_count": int(session.position_count or 1),
        "booked_count": session.booked_count,
        "start_hour": start.hour,
        "start_minute": start.minute,
        "end_hour": end_hour,
        "end_minute": end_minute,
        "date": start.strftime("%Y-%m-%d"),
        "date_label": start.strftime("%A %d %B %Y"),
        "time_label": f"{start.strftime('%H:%M')} – {end.strftime('%H:%M')}",
        "positions_label": "" if actor.is_client else session.positions_label,
        "positions_short": "" if actor.is_client else f"{session.booked_count}/{int(session.position_count or 1)}",
        "is_partial": show_partial,
        "show_partial": show_partial,
        "viewer_is_client": bool(actor.is_client),
        "booked_by_me": booked_by_me,
        "is_full": session.is_full,
        "interested_by_me": interested_by_me,
        "can_interest": can_interest,
        "has_interest": bool(can_manage and session.is_full and session.interests),
        "display_status": display_status,
        "display_status_label": display_status_label,
        "booked_percent": round(
            100.0 * session.booked_count / max(1, int(session.position_count or 1)),
            4,
        ),
        "instructor": session.instructor.display_name if session.instructor else "",
        "clients": [
            {"id": client.id, "name": client.display_name}
            for client in session.booked_clients
        ],
        "interested": [
            {"id": client.id, "name": client.display_name}
            for client in session.interested_clients
        ]
        if can_manage
        else [],
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
        if data["can_interest"]:
            data["interest_url"] = f"/sessions/{session.id}/interest"
            data["interest_remove_url"] = f"/sessions/{session.id}/withdraw-interest"
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


def block_geometry(session, day_date=None):
    if session is None:
        return None
    if day_date is None:
        day_date = session.datetime_start.date()
    block = _block_for_day(session, day_date)
    if not block:
        return None
    return {"top": block["top"], "height": block["height"]}


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
