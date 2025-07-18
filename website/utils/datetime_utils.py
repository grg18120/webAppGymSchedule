from datetime import datetime
import calendar


def string_to_datetime(date_string: str, date_format: str = "%Y-%m-%d"):
    try:
        return datetime.strptime(date_string, date_format)
    except ValueError:
        return None
    

def get_days_in_month(year: int, month: int) -> list[datetime]:
    num_days = calendar.monthrange(year, month)[1]
    return [datetime(year, month, day) for day in range(1, num_days + 1)]


def datetime_zero_time(datetime_obj, hour = 0, min= 0, sec= 0, micro_sec= 0):
    return datetime_obj.replace(hour=hour, minute=min, second=sec, microsecond=micro_sec)

def datetime_days_delta(dt1, dt2):
    return (datetime_zero_time(dt1) - datetime_zero_time(dt2)).days
