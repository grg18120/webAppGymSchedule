from . import db
from flask_login import UserMixin
from sqlalchemy.sql import func

# from website.models import User

class ScheduleTime(db.Model, UserMixin):
    __tablename__ = 'schedule_time'

    id = db.Column(db.Integer, primary_key=True)
    time_start = db.Column(db.DateTime(timezone=True), unique=True)
    time_end = db.Column(db.DateTime(timezone=True), unique=True)
    time_bookable = db.Column(db.Boolean, default=False)
    date_id = db.Column(db.Integer, db.ForeignKey('schedule_date.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))


class ScheduleDate(db.Model, UserMixin):
    __tablename__ = 'schedule_date'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime(timezone=True), unique=True)
    date_bookable = db.Column(db.Integer, default=0)
    schedule_time = db.relationship('ScheduleTime')


class User(db.Model, UserMixin):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True)
    password = db.Column(db.String(150))
    name_first = db.Column(db.String(150))
    name_last = db.Column(db.String(150))
    date_created = db.Column(db.DateTime(timezone=True), default=func.now())
    disabled = db.Column(db.Boolean, default=False)
    schedule_time = db.relationship('ScheduleTime')


class SingUpCode(db.Model, UserMixin):

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(150), unique=True)
    date_created = db.Column(db.DateTime(timezone=True), default=func.now())
    is_valid = db.Column(db.Boolean, default=True)



