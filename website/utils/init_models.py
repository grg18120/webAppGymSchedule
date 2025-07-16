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








