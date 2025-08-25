from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash



def generate_hourly_datetimes(for_date: datetime.date) -> list[datetime]:
    return [
        datetime.combine(for_date, datetime.min.time()) + timedelta(hours=i)
        for i in range(24)
    ]


# def init_ScheduleDate_table(db):
#     from website.models import ScheduleDate, ScheduleTime

#     start_date = datetime.now().date() + timedelta(days=-1)
#     end_date = start_date + timedelta(days=365)

#     for i in range((end_date - start_date).days + 1):
#         date_obj = datetime.combine(start_date + timedelta(days=i), datetime.min.time())
#         schedule_date_obj = ScheduleDate(date=date_obj, date_bookable=1)
#         db.session.add(schedule_date_obj)
#         for tim in generate_hourly_datetimes(date_obj):
#             schedule_time_obj = ScheduleTime(time_start=tim, time_end=tim + timedelta(hours=0.5), date_id= schedule_date_obj.id)
#             db.session.add(schedule_time_obj)
#             schedule_time_obj = ScheduleTime(time_start=tim + timedelta(hours=0.5), time_end=tim + timedelta(hours=1.0), date_id= schedule_date_obj.id)
#             db.session.add(schedule_time_obj)

#     db.session.commit()


def init_database(db):
    init_User_table(db)
    init_Trainer_table(db)
    init_ScheduleTrainning_table(db)


def init_User_table(db):
    from website.models import User
    user = User(
        email="admin@admin.com",
        password=generate_password_hash("admin"),
        name_first="admin",
        name_last="admin",
    )
    db.session.add(user)
    db.session.commit()


def init_Trainer_table(db):
    from website.models import Trainer
    trainer = Trainer(
        email="pavlos@pavlos.com",
        password=generate_password_hash("pavlos"),
        name_first="pavlos",
        name_last="papadakis",
    )
    db.session.add(trainer)
    db.session.commit()


def init_ScheduleTrainning_table(db):
    from website.models import ScheduleTrainning, Trainer, User
    
    schedule_trainning = ScheduleTrainning(
        datetime_start = datetime(2025, 8, 24, 19, 0),
        datetime_end = datetime(2025, 8, 24, 20, 0),
        trainer_id = Trainer.query.filter(Trainer.name_first == "pavlos").first().id,
        user_id = User.query.filter(User.name_first == "admin").first().id
    )
    db.session.add(schedule_trainning)
    db.session.commit()

    schedule_trainning = ScheduleTrainning(
    datetime_start = datetime(2025, 8, 24, 20, 0),
    datetime_end = datetime(2025, 8, 24, 21, 0),
    trainer_id = Trainer.query.filter(Trainer.name_first == "pavlos").first().id,
    user_id = User.query.filter(User.name_first == "admin").first().id
    )
    db.session.add(schedule_trainning)
    db.session.commit()

    schedule_trainning = ScheduleTrainning(
    datetime_start = datetime(2025, 8, 24, 21, 0),
    datetime_end = datetime(2025, 8, 24, 22, 0),
    trainer_id = Trainer.query.filter(Trainer.name_first == "pavlos").first().id,
    )
    db.session.add(schedule_trainning)
    db.session.commit()

    for m in range(1,13):
        schedule_trainning = ScheduleTrainning(
            datetime_start = datetime(2025, m, 20, 12, 0),
            datetime_end = datetime(2025, m, 20, 14, 0),
            trainer_id = Trainer.query.filter(Trainer.name_first == "pavlos").first().id
        )
        db.session.add(schedule_trainning)
        db.session.commit()

        schedule_trainning = ScheduleTrainning(
            datetime_start = datetime(2026, m, 20, 12, 0),
            datetime_end = datetime(2026, m, 20, 14, 0),
            trainer_id = Trainer.query.filter(Trainer.name_first == "pavlos").first().id
        )
        db.session.add(schedule_trainning)
        db.session.commit()








