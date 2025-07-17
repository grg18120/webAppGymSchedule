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