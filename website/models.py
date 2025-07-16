from . import db
from flask_login import UserMixin
from sqlalchemy.sql import func
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime




class SerializerMixin:
    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class User(db.Model, UserMixin):
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    name_first = db.Column(db.String(150), nullable=False)
    name_last = db.Column(db.String(150), nullable=False)
    date_birth = db.Column(db.DateTime)
    address = db.Column(db.String(150))
    date_created = db.Column(db.DateTime(timezone=True), default=func.now())
    discount = db.Column(db.Float, default=0.0)
    status = db.Column(db.Integer, default=1) # 0: inactive,  1: active

    # body_reports = db.relationship('Body', backref='user', lazy=True)
    # training_schedules = db.relationship('ScheduleTrain', backref='user', lazy=True)


class Body(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    weight_kg = db.Column(db.Float)
    muscle_mass_kg = db.Column(db.Float)
    datetime_report = db.Column(db.DateTime(timezone=True), default=func.now())


    # user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


class Trainer(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    name_first = db.Column(db.String(150))
    name_last = db.Column(db.String(150))
    datetime_created = db.Column(db.DateTime(timezone=True), default=func.now())
    status = db.Column(db.Integer, default=1)

    # trainings = db.relationship('TrainerTraining', backref='trainer', lazy=True)
    # locations = db.relationship('TrainLocation', backref='trainer', lazy=True)
    # schedule_trains = db.relationship('ScheduleTrain', backref='trainer', lazy=True)


class Training(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    desc = db.Column(db.String)
    status = db.Column(db.Integer, default=1)
    duration_hours = db.Column(db.Float)
    cost_hourly = db.Column(db.Float)

    # trainers = db.relationship('TrainerTraining', backref='training', lazy=True)
    # locations = db.relationship('TrainLocation', backref='training', lazy=True)
    # schedule_trains = db.relationship('ScheduleTrain', backref='training', lazy=True)


class TrainerTraining(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    trainer_id = db.Column(db.Integer, db.ForeignKey('trainer.id'), nullable=False)
    training_id = db.Column(db.Integer, db.ForeignKey('training.id'), nullable=False)


# class TrainLocation(db.Model, UserMixin):
#     id = db.Column(db.Integer, primary_key=True)
#     address = db.Column(db.String(150))

    # trainer_id = db.Column(db.Integer, db.ForeignKey('trainer.id'), nullable=False)
    # training_id = db.Column(db.Integer, db.ForeignKey('training.id'), nullable=False)
    # equipments = db.relationship('TrainEquipment', backref='location', lazy=True)
    # schedules = db.relationship('ScheduleTrain', backref='location', lazy=True)


# class TrainEquipment(db.Model, UserMixin):
#     id = db.Column(db.Integer, primary_key=True)
#     desc = db.Column(db.String(150))
#     quantity = db.Column(db.Integer)
#     datetime_buy = db.Column(db.Integer)

    # training_location_id = db.Column(db.Integer, db.ForeignKey('train_location.id'), nullable=False)


class ScheduleTrain(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    datetime_created = db.Column(db.DateTime, default=datetime.utcnow)
    datetime_end = db.Column(db.DateTime)


    # trainer_id = db.Column(db.Integer, db.ForeignKey('trainer.id'), nullable=False)
    # user_id = db.Column(db.Integer, db.ForeignKey('user.id'), default=None)
    # training_id = db.Column(db.Integer, db.ForeignKey('training.id'), nullable=False)
    # location_id = db.Column(db.Integer, db.ForeignKey('train_location.id'), nullable=False)




