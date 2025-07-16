from datetime import datetime


def string_to_datetime(date_string: str, date_format: str = "%Y-%m-%d"):
    try:
        return datetime.strptime(date_string, date_format)
    except ValueError:
        return None