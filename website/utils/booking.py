from datetime import datetime, timedelta

from sqlalchemy import extract
from sqlalchemy.exc import IntegrityError

from website import db
from website.models import (
    POSITION_COUNT_MAX,
    POSITION_COUNT_MIN,
    ROLE_ADMIN,
    ROLE_CLIENT,
    ROLE_INSTRUCTOR,
    SESSION_AVAILABLE,
    SESSION_BOOKED,
    SESSION_CANCELLED,
    GymSession,
    GymSessionBooking,
    User,
)
from website.utils.timeutils import now_gym

CLOCK_HOURS = tuple(range(0, 25))
CLOCK_MINUTES = (0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55)
SLOT_LENGTH_MINUTES = tuple(range(5, 181, 5))
BREAK_MINUTES = tuple(range(0, 61, 5))


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


def reconcile_overlapping_sessions():
    """Cancel later overlapping active slots for the same instructor.

    Booked sessions win over available ones. Adjacent slots that only
    touch at an endpoint (10:00-11:00 and 11:00-12:00) are kept.
    """
    instructor_ids = [
        row[0]
        for row in db.session.query(GymSession.instructor_id).distinct().all()
        if row[0] is not None
    ]
    cancelled = 0
    for instructor_id in instructor_ids:
        sessions = (
            GymSession.query.filter(
                GymSession.instructor_id == instructor_id,
                GymSession.status != SESSION_CANCELLED,
            )
            .order_by(GymSession.id)
            .all()
        )
        kept = []
        for session in sessions:
            clashes = [
                other
                for other in kept
                if other.datetime_start < session.datetime_end
                and other.datetime_end > session.datetime_start
            ]
            if not clashes:
                kept.append(session)
                continue
            booked_clashes = [other for other in clashes if other.status == SESSION_BOOKED]
            if session.status == SESSION_BOOKED and not booked_clashes:
                for other in clashes:
                    _cancel_session_occupancy(other)
                    kept.remove(other)
                    cancelled += 1
                kept.append(session)
            else:
                _cancel_session_occupancy(session)
                cancelled += 1
    if cancelled:
        db.session.commit()
    return cancelled


def parse_position_count(value, default=1):
    if value is None or value == "":
        value = default
    try:
        count = int(value)
    except (TypeError, ValueError):
        return None, f"Positions must be a number from {POSITION_COUNT_MIN} to {POSITION_COUNT_MAX}."
    if count < POSITION_COUNT_MIN or count > POSITION_COUNT_MAX:
        return None, f"Positions must be a number from {POSITION_COUNT_MIN} to {POSITION_COUNT_MAX}."
    return count, None


def _cancel_session_occupancy(session):
    session.status = SESSION_CANCELLED
    session.client_id = None
    session.bookings.clear()


def create_availability(instructor, start, end, commit=True, position_count=1):
    if instructor.role not in (ROLE_INSTRUCTOR, ROLE_ADMIN):
        return None, "Only instructors can publish availability."
    if end <= start:
        return None, "End time must be after start time."
    if start <= now_gym():
        return None, "Cannot create availability in the past."
    count, error = parse_position_count(position_count)
    if error:
        return None, error
    if overlapping_sessions(instructor.id, start, end):
        return None, "This time overlaps an existing session for that instructor."

    session = GymSession(
        instructor_id=instructor.id,
        datetime_start=start,
        datetime_end=end,
        status=SESSION_AVAILABLE,
        position_count=count,
    )
    try:
        with db.session.begin_nested():
            db.session.add(session)
            db.session.flush()
    except IntegrityError:
        return None, "This time overlaps an existing session for that instructor."
    if commit:
        db.session.commit()
    return session, None


def publish_hourly_slots(instructor, day_date, start_hour=9, end_hour=22, position_count=1):
    created = 0
    skipped = 0
    for hour in range(start_hour, end_hour):
        start = day_date.replace(hour=hour, minute=0, second=0, microsecond=0)
        end = day_date.replace(hour=hour + 1, minute=0, second=0, microsecond=0)
        session, error = create_availability(
            instructor, start, end, commit=False, position_count=position_count
        )
        if error:
            skipped += 1
            continue
        created += 1
    if created:
        db.session.commit()
    else:
        db.session.rollback()
    return created, skipped


def publish_range_slots(
    instructor, range_start, range_end, slot_minutes, break_minutes=0, position_count=1
):
    if slot_minutes <= 0:
        return 0, 0, "Slot length must be greater than 0 minutes."
    if break_minutes < 0:
        return 0, 0, "Break time cannot be negative."
    if range_end <= range_start:
        return 0, 0, "Range end must be after range start."
    created = 0
    skipped = 0
    start = range_start
    slot = timedelta(minutes=slot_minutes)
    pause = timedelta(minutes=break_minutes)
    while start + slot <= range_end:
        end = start + slot
        _session, error = create_availability(
            instructor, start, end, commit=False, position_count=position_count
        )
        if error:
            skipped += 1
        else:
            created += 1
        start = end + pause
    if created:
        db.session.commit()
    else:
        db.session.rollback()
    return created, skipped, None


def _datetime_at(day, hour, minute):
    midnight = datetime(day.year, day.month, day.day)
    if hour == 24:
        return midnight + timedelta(days=1)
    return midnight.replace(hour=hour, minute=minute)


def publish_week_slots(
    instructor,
    days,
    start_hour,
    start_minute,
    end_hour,
    end_minute,
    slot_minutes,
    break_minutes=0,
    position_count=1,
):
    if start_hour not in CLOCK_HOURS or end_hour not in CLOCK_HOURS:
        return 0, 0, "Choose a range using 24-hour hours."
    if start_minute not in CLOCK_MINUTES or end_minute not in CLOCK_MINUTES:
        return 0, 0, "Choose minutes in 5-minute steps."
    if start_hour == 24 and start_minute != 0:
        return 0, 0, "Hour 24 must be 24:00."
    if end_hour == 24 and end_minute != 0:
        return 0, 0, "Hour 24 must be 24:00."
    if slot_minutes not in SLOT_LENGTH_MINUTES:
        return 0, 0, "Choose a valid slot length."
    if break_minutes not in BREAK_MINUTES:
        return 0, 0, "Choose a valid break time."
    start_mins = start_hour * 60 + start_minute
    end_mins = end_hour * 60 + end_minute
    if end_mins <= start_mins:
        return 0, 0, "Range end must be after range start."

    created = 0
    skipped = 0
    slot = timedelta(minutes=slot_minutes)
    pause = timedelta(minutes=break_minutes)
    for day in days:
        range_start = _datetime_at(day, start_hour, start_minute)
        range_end = _datetime_at(day, end_hour, end_minute)
        start = range_start
        while start + slot <= range_end:
            end = start + slot
            _session, error = create_availability(
                instructor, start, end, commit=False, position_count=position_count
            )
            if error:
                skipped += 1
            else:
                created += 1
            start = end + pause
    if created:
        db.session.commit()
    else:
        db.session.rollback()
    return created, skipped, None


def _instructor_day_query(instructor, year, month, day, status):
    return GymSession.query.filter(
        GymSession.instructor_id == instructor.id,
        GymSession.status == status,
        extract("year", GymSession.datetime_start) == year,
        extract("month", GymSession.datetime_start) == month,
        extract("day", GymSession.datetime_start) == day,
    )


def actor_can_manage_instructor(actor, instructor):
    if not instructor or not instructor.is_instructor:
        return False
    return actor.is_admin or (actor.is_instructor and actor.id == instructor.id)


def delete_slots_on_day(actor, instructor, year, month, day, status):
    if not actor_can_manage_instructor(actor, instructor):
        return 0, "You can only change your own slots."
    if status not in (SESSION_AVAILABLE, SESSION_BOOKED):
        return 0, "That slot type cannot be deleted in bulk."
    query = _instructor_day_query(instructor, year, month, day, status)
    slots = query.all()
    deleted = []
    for slot in slots:
        if status == SESSION_AVAILABLE and slot.booked_count > 0:
            continue
        deleted.append(slot)
    count = len(deleted)
    for slot in deleted:
        db.session.delete(slot)
    db.session.commit()
    return count, None


def cancel_booked_slots_on_day(actor, instructor, year, month, day):
    if not actor_can_manage_instructor(actor, instructor):
        return 0, "You can only change your own slots."
    slots = GymSession.query.filter(
        GymSession.instructor_id == instructor.id,
        GymSession.status != SESSION_CANCELLED,
        extract("year", GymSession.datetime_start) == year,
        extract("month", GymSession.datetime_start) == month,
        extract("day", GymSession.datetime_start) == day,
    ).all()
    count = 0
    for slot in slots:
        if slot.is_past or slot.booked_count == 0:
            continue
        _cancel_session_occupancy(slot)
        count += 1
    db.session.commit()
    return count, None


def delete_booked_session(session, actor):
    """Hard-delete a booked session, including past ones. Admin only."""
    if not session:
        return False, "Session not found."
    if session.status != SESSION_BOOKED:
        return False, "Only booked sessions can be deleted this way."
    if not actor.is_admin:
        return False, "Only an admin can delete a booked session."

    db.session.delete(session)
    db.session.commit()
    return True, "Booked session deleted."


def book_session(session, client):
    if client.role != ROLE_CLIENT:
        return False, "Only clients can book a training session."
    if not session:
        return False, "Session not found."
    if session.datetime_start <= now_gym():
        return False, "Past sessions cannot be booked."
    if session.status == SESSION_CANCELLED:
        return False, "That session is no longer available."
    if session.is_booked_by(client):
        return False, "You already have a place on this session."
    if session.free_count <= 0:
        return False, "That session is no longer available."

    try:
        with db.session.begin_nested():
            db.session.add(GymSessionBooking(session_id=session.id, client_id=client.id))
            db.session.flush()
            taken = (
                db.session.query(GymSessionBooking)
                .filter_by(session_id=session.id)
                .count()
            )
            if taken > int(session.position_count or 1):
                raise IntegrityError("session is full", None, None)
    except IntegrityError:
        return False, "That session is no longer available."

    db.session.expire(session, ["bookings"])
    session.sync_status()
    db.session.commit()
    db.session.expire(session)
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
        allowed = session.is_booked_by(actor)
    else:
        allowed = False

    if not allowed:
        return False, "You cannot cancel this session."

    if actor.is_client:
        for row in list(session.bookings):
            if row.client_id == actor.id:
                db.session.delete(row)
        if session.client_id == actor.id:
            session.client_id = None
        db.session.flush()
        db.session.expire(session, ["bookings"])
        session.sync_status()
        db.session.commit()
        return True, "Booking cancelled. The slot is available again."

    _cancel_session_occupancy(session)
    db.session.commit()
    return True, "Session cancelled."


def remove_availability(session, actor):
    if not session:
        return False, "Session not found."
    if session.status != SESSION_AVAILABLE or session.booked_count > 0:
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
            if s.is_available or s.is_booked_by(actor)
        ]
    return sessions


def instructors():
    return (
        User.query.filter_by(role=ROLE_INSTRUCTOR, status=1)
        .order_by(User.name_last, User.name_first)
        .all()
    )
