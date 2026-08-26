from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from website.models import (
    ROLE_ADMIN,
    ROLE_CLIENT,
    ROLE_INSTRUCTOR,
    SESSION_AVAILABLE,
    SESSION_BOOKED,
    GymSession,
    User,
)


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
)


def init_database(db):
    _ensure_demo_users(db)
    _ensure_demo_sessions(db)


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


def _next_hour(now=None):
    now = now or datetime.now()
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
