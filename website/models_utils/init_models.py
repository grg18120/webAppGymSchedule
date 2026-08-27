from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

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
from website.utils.timeutils import now_gym


DEMO_ACCOUNTS = (
    {
        "email": "admin@gym.com",
        "password": "admin123",
        "name_first": "Ada",
        "name_last": "Admin",
        "role": ROLE_ADMIN,
    },
    {
        "email": "instructor@gym.com",
        "password": "instructor123",
        "name_first": "Alex",
        "name_last": "Instructor",
        "role": ROLE_INSTRUCTOR,
    },
    {
        "email": "client@gym.com",
        "password": "client123",
        "name_first": "Casey",
        "name_last": "Client",
        "role": ROLE_CLIENT,
    },
    {
        "email": "jordan@gym.com",
        "password": "client123",
        "name_first": "Jordan",
        "name_last": "Lee",
        "role": ROLE_CLIENT,
    },
    {
        "email": "riley@gym.com",
        "password": "client123",
        "name_first": "Riley",
        "name_last": "Patel",
        "role": ROLE_CLIENT,
    },
    {
        "email": "morgan@gym.com",
        "password": "client123",
        "name_first": "Morgan",
        "name_last": "Chen",
        "role": ROLE_CLIENT,
    },
)


def init_database(db):
    _ensure_demo_users(db)
    _ensure_single_instructor(db)
    _ensure_demo_sessions(db)
    _ensure_extra_client_bookings(db)
    _ensure_jul_aug_sep_sessions(db)


def _ensure_demo_users(db):
    for account in DEMO_ACCOUNTS:
        existing = User.query.filter_by(email=account["email"]).first()
        if existing:
            continue
        db.session.add(
            User(
                email=account["email"],
                password=generate_password_hash(account["password"]),
                name_first=account["name_first"],
                name_last=account["name_last"],
                role=account["role"],
                status=1,
            )
        )
    db.session.commit()


def _ensure_single_instructor(db):
    keep = User.query.filter_by(email="instructor@gym.com").first()
    extras_query = User.query.filter(User.role == ROLE_INSTRUCTOR)
    if keep:
        extras_query = extras_query.filter(User.id != keep.id)
    extras = extras_query.all()
    if not extras:
        return
    if not keep:
        keep = extras[0]
        extras = extras[1:]
        if not extras:
            return
    keep_id = keep.id
    extra_ids = [extra.id for extra in extras]
    for extra_id in extra_ids:
        extra_sessions = GymSession.query.filter_by(instructor_id=extra_id).all()
        for session in extra_sessions:
            clash = GymSession.query.filter_by(
                instructor_id=keep_id,
                datetime_start=session.datetime_start,
            ).first()
            if clash:
                db.session.delete(session)
        db.session.flush()
        # Remap then SQL-delete the extra user. ORM User.delete() would
        # null instructor_id via the instructed_sessions backref.
        GymSession.query.filter_by(instructor_id=extra_id).update(
            {GymSession.instructor_id: keep_id},
            synchronize_session=False,
        )
        User.query.filter_by(id=extra_id).delete(synchronize_session=False)
        db.session.expire_all()
    db.session.commit()


def _next_hour(now=None):
    now = now or now_gym()
    return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def _ensure_demo_sessions(db):
    instructor = User.query.filter_by(email="instructor@gym.com").first()
    client = User.query.filter_by(email="client@gym.com").first()
    if not instructor or not client:
        return
    if GymSession.query.filter_by(instructor_id=instructor.id).count() > 0:
        return

    base = _next_hour()
    offsets = (0, 2, 24, 26)
    for index, hour_offset in enumerate(offsets):
        start = base + timedelta(hours=hour_offset)
        session = GymSession(
            instructor_id=instructor.id,
            datetime_start=start,
            datetime_end=start + timedelta(hours=1),
            status=SESSION_AVAILABLE,
        )
        if index == 2:
            session.client_id = client.id
            session.status = SESSION_BOOKED
        db.session.add(session)
    db.session.commit()


def _ensure_extra_client_bookings(db):
    instructor = User.query.filter_by(email="instructor@gym.com").first()
    if not instructor:
        return

    extra_bookings = (
        ("jordan@gym.com", 48),
        ("riley@gym.com", 50),
        ("morgan@gym.com", 72),
        ("client@gym.com", -72),
        ("jordan@gym.com", -48),
    )
    base = _next_hour()
    created = False
    for email, hour_offset in extra_bookings:
        client = User.query.filter_by(email=email).first()
        if not client:
            continue
        start = base + timedelta(hours=hour_offset)
        created = (
            _add_session_if_missing(
                db, instructor, start, start + timedelta(hours=1), client
            )
            or created
        )
    if created:
        db.session.commit()


def _add_session_if_missing(db, instructor, start, end, client=None):
    existing = GymSession.query.filter(
        GymSession.instructor_id == instructor.id,
        GymSession.datetime_start == start,
        GymSession.status != SESSION_CANCELLED,
    ).first()
    if existing:
        return False
    session = GymSession(
        instructor_id=instructor.id,
        datetime_start=start,
        datetime_end=end,
        status=SESSION_BOOKED if client else SESSION_AVAILABLE,
        client_id=client.id if client else None,
    )
    db.session.add(session)
    return True


def _ensure_jul_aug_sep_sessions(db):
    instructor = User.query.filter_by(email="instructor@gym.com").first()
    clients = [
        User.query.filter_by(email=email).first()
        for email in ("client@gym.com", "jordan@gym.com", "riley@gym.com", "morgan@gym.com")
    ]
    clients = [client for client in clients if client]
    if not instructor or not clients:
        return

    year = now_gym().year
    booked_days = (
        (7, 3, 10, clients[0]),
        (7, 8, 11, clients[1 % len(clients)]),
        (7, 15, 9, clients[2 % len(clients)]),
        (7, 22, 16, clients[0]),
        (7, 28, 10, clients[1 % len(clients)]),
        (8, 5, 10, clients[2 % len(clients)]),
        (8, 12, 14, clients[0]),
        (8, 20, 9, clients[3 % len(clients)]),
        (8, 27, 11, clients[1 % len(clients)]),
        (9, 2, 10, clients[0]),
        (9, 10, 15, clients[2 % len(clients)]),
        (9, 18, 9, clients[1 % len(clients)]),
    )
    open_days = (
        (8, 28, 9),
        (8, 30, 11),
        (9, 2, 14),
        (9, 3, 10),
        (9, 8, 13),
        (9, 15, 9),
        (9, 22, 16),
        (9, 25, 10),
    )
    created = False
    for month, day, hour, client in booked_days:
        start = datetime(year, month, day, hour, 0)
        created = _add_session_if_missing(db, instructor, start, start + timedelta(hours=1), client) or created
    for month, day, hour in open_days:
        start = datetime(year, month, day, hour, 0)
        created = _add_session_if_missing(db, instructor, start, start + timedelta(hours=1), None) or created
    if created:
        db.session.commit()
