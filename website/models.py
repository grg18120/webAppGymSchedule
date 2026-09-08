from datetime import datetime

from flask_login import UserMixin
from sqlalchemy import Index, UniqueConstraint, text
from sqlalchemy.sql import func

from . import db
from website.utils.timeutils import now_gym

ROLE_ADMIN = "admin"
ROLE_INSTRUCTOR = "instructor"
ROLE_CLIENT = "client"
ROLES = (ROLE_ADMIN, ROLE_INSTRUCTOR, ROLE_CLIENT)

SESSION_AVAILABLE = "available"
SESSION_BOOKED = "booked"
SESSION_CANCELLED = "cancelled"

POSITION_COUNT_MIN = 1
POSITION_COUNT_MAX = 20


class SerializerMixin:
    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class User(db.Model, UserMixin, SerializerMixin):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    name_first = db.Column(db.String(150), nullable=False)
    name_last = db.Column(db.String(150), nullable=False)
    date_birth = db.Column(db.DateTime)
    address = db.Column(db.String(150))
    date_created = db.Column(db.DateTime(timezone=True), default=func.now())
    discount = db.Column(db.Float, default=0.0)
    status = db.Column(db.Integer, default=1)  # 0 inactive, 1 active
    role = db.Column(db.String(20), nullable=False, default=ROLE_CLIENT)

    @property
    def is_active(self):
        return self.status == 1

    @property
    def is_admin(self):
        return self.role == ROLE_ADMIN

    @property
    def is_instructor(self):
        return self.role == ROLE_INSTRUCTOR

    @property
    def is_client(self):
        return self.role == ROLE_CLIENT

    @property
    def display_name(self):
        return f"{self.name_first} {self.name_last}".strip()

    @property
    def role_label(self):
        return {
            ROLE_ADMIN: "Admin",
            ROLE_INSTRUCTOR: "Instructor",
            ROLE_CLIENT: "Client",
        }.get(self.role, self.role)


class GymSessionBooking(db.Model, SerializerMixin):
    __tablename__ = "gym_session_booking"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("gym_session.id"), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    client = db.relationship("User")

    __table_args__ = (UniqueConstraint("session_id", "client_id", name="ux_gym_session_booking_client"),)


class GymSession(db.Model, SerializerMixin):
    __tablename__ = "gym_session"

    id = db.Column(db.Integer, primary_key=True)
    datetime_created = db.Column(db.DateTime, default=datetime.now)
    datetime_start = db.Column(db.DateTime, nullable=False)
    datetime_end = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default=SESSION_AVAILABLE)
    position_count = db.Column(db.Integer, nullable=False, default=1)

    instructor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    instructor = db.relationship("User", foreign_keys=[instructor_id], backref="instructed_sessions")
    client = db.relationship("User", foreign_keys=[client_id], backref="booked_sessions")
    bookings = db.relationship(
        "GymSessionBooking",
        backref="session",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index(
            "ux_gym_session_instructor_start_active",
            "instructor_id",
            "datetime_start",
            unique=True,
            sqlite_where=text("status != 'cancelled'"),
        ),
    )

    @property
    def duration_minutes(self):
        return int((self.datetime_end - self.datetime_start).total_seconds() / 60)

    @property
    def is_past(self):
        return self.datetime_start <= now_gym()

    @property
    def booked_count(self):
        if self.bookings:
            return len(self.bookings)
        return 1 if self.client_id else 0

    @property
    def free_count(self):
        return max(0, int(self.position_count or 1) - self.booked_count)

    @property
    def is_full(self):
        return self.booked_count >= int(self.position_count or 1)

    @property
    def is_partial(self):
        return self.booked_count > 0 and not self.is_full

    @property
    def booked_clients(self):
        clients = [booking.client for booking in self.bookings if booking.client]
        if clients:
            return clients
        if self.client:
            return [self.client]
        return []

    @property
    def positions_label(self):
        return f"Positions: {self.booked_count}/{self.position_count}"

    def is_booked_by(self, user):
        if not user:
            return False
        if any(booking.client_id == user.id for booking in self.bookings):
            return True
        if self.bookings:
            return False
        return self.client_id == user.id

    def sync_status(self):
        if self.status == SESSION_CANCELLED:
            return
        occupied = len(self.bookings)
        self.status = SESSION_BOOKED if occupied >= int(self.position_count or 1) else SESSION_AVAILABLE
        first = self.bookings[0] if self.bookings else None
        self.client_id = first.client_id if first else None

    @property
    def is_available(self):
        return (
            self.status != SESSION_CANCELLED
            and not self.is_past
            and self.free_count > 0
        )

    @property
    def status_label(self):
        if self.status == SESSION_CANCELLED:
            return "Cancelled"
        if self.is_past and self.status == SESSION_BOOKED:
            return "Completed"
        if self.is_past:
            return "Past"
        if self.status == SESSION_BOOKED:
            return "Booked"
        if self.is_partial:
            return "Open & Booked"
        return "Available"
