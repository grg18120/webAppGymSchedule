from datetime import datetime

from flask_login import UserMixin
from sqlalchemy import Index, text
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


class GymSession(db.Model, SerializerMixin):
    __tablename__ = "gym_session"

    id = db.Column(db.Integer, primary_key=True)
    datetime_created = db.Column(db.DateTime, default=datetime.now)
    datetime_start = db.Column(db.DateTime, nullable=False)
    datetime_end = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default=SESSION_AVAILABLE)

    instructor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    instructor = db.relationship("User", foreign_keys=[instructor_id], backref="instructed_sessions")
    client = db.relationship("User", foreign_keys=[client_id], backref="booked_sessions")

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
    def is_available(self):
        return self.status == SESSION_AVAILABLE and not self.is_past and self.client_id is None

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
        return "Available"
