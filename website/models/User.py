
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

from . import db
from flask_login import UserMixin
from sqlalchemy.sql import func

db = SQLAlchemy()

class SerializerMixin:
    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class User(db.Model, SerializerMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    name_first = db.Column(db.String(150))
    name_last = db.Column(db.String(150))
    date_birth = db.Column(db.DateTime)
    address = db.Column(db.String(150))
    date_created = db.Column(db.DateTime(timezone=True), default=func.now())
    discount = db.Column(db.Float, default = 0.0) 
    status = db.Column(db.Integer, default=1) 

    # body_reports = db.relationship('Body', backref='user', lazy=True)
    # training_schedules = db.relationship('ScheduleTrain', backref='user', lazy=True)