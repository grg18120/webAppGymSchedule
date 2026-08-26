from datetime import datetime

from sqlalchemy import extract

from website import db
from website.models import (
    ROLE_ADMIN,
    ROLE_CLIENT,
    ROLE_INSTRUCTOR,
    SESSION_AVAILABLE,
    SESSION_BOOKED,
    SESSION_CANCELLED,
    GymSession,
    User,
)


def overlapping_sessions(instructor_id, start, end, exclude_id=None):
    query = GymSession.query.filter(
        GymSession.instructor_id == instructor_id,
        GymSession.status != SESSION_CANCELLED,
        GymSession.datetime_start < end,
        GymSession.datetime_end > start,
    )
    if exclude_id is not None:
        query = query.filter(GymSession.id != exclude_id)
    return query.all()


def create_availability(instructor, start, end):
    if instructor.role not in (ROLE_INSTRUCTOR, ROLE_ADMIN):
        return None, "Only instructors can publish availability."
    if end <= start:
        return None, "End time must be after start time."
    if start <= datetime.now():
        return None, "Cannot create availability in the past."
    if overlapping_sessions(instructor.id, start, end):
        return None, "This time overlaps an existing session for that instructor."

    session = GymSession(
        instructor_id=instructor.id,
        datetime_start=start,
        datetime_end=end,
        status=SESSION_AVAILABLE,
    )
    db.session.add(session)
    db.session.commit()
    return session, None


def book_session(session, client):
    if client.role != ROLE_CLIENT:
        return False, "Only clients can book a training session."
    if not session:
        return False, "Session not found."
    if session.status != SESSION_AVAILABLE or session.client_id is not None:
        return False, "That session is no longer available."
    if session.datetime_start <= datetime.now():
        return False, "Past sessions cannot be booked."

    session.client_id = client.id
    session.status = SESSION_BOOKED
    db.session.commit()
    return True, "Session booked. See it under My sessions."


def cancel_session(session, actor):
    if not session:
        return False, "Session not found."
    if session.status == SESSION_CANCELLED:
        return False, "That session is already cancelled."
    if session.is_past:
        return False, "Past sessions cannot be cancelled."

    if actor.is_admin:
        allowed = True
    elif actor.is_instructor:
        allowed = session.instructor_id == actor.id
    elif actor.is_client:
        allowed = session.client_id == actor.id and session.status == SESSION_BOOKED
    else:
        allowed = False

    if not allowed:
        return False, "You cannot cancel this session."

    if actor.is_client:
        session.client_id = None
        session.status = SESSION_AVAILABLE
        db.session.commit()
        return True, "Booking cancelled. The slot is available again."

    session.status = SESSION_CANCELLED
    session.client_id = None
    db.session.commit()
    return True, "Session cancelled."


def remove_availability(session, actor):
    if not session:
        return False, "Session not found."
    if session.status != SESSION_AVAILABLE:
        return False, "Only open (unbooked) slots can be removed."
    if not actor.is_admin and session.instructor_id != actor.id:
        return False, "You can only remove your own availability."

    db.session.delete(session)
    db.session.commit()
    return True, "Availability removed."


def sessions_on_day(year, month, day, actor, instructor_id=None):
    query = GymSession.query.filter(
        GymSession.status != SESSION_CANCELLED,
        extract("year", GymSession.datetime_start) == year,
        extract("month", GymSession.datetime_start) == month,
        extract("day", GymSession.datetime_start) == day,
    )
    if instructor_id:
        query = query.filter(GymSession.instructor_id == instructor_id)
    elif actor.is_instructor:
        query = query.filter(GymSession.instructor_id == actor.id)

    sessions = query.order_by(GymSession.datetime_start).all()
    if actor.is_client:
        return [
            s
            for s in sessions
            if s.is_available or s.client_id == actor.id
        ]
    return sessions


def instructors():
    return (
        User.query.filter_by(role=ROLE_INSTRUCTOR, status=1)
        .order_by(User.name_last, User.name_first)
        .all()
    )
